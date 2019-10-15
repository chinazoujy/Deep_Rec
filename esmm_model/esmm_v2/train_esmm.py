#!/data/venv/hdp-env/bin python
# -*- coding: utf8 -*-
# @Author  : shixiangfu
import sys
sys.path.append("..")
import tensorflow as tf
from alg_utils.utils_tf import load_json_from_file,get_input_schema_spec
from esmm import esmm,export_model
'''nohup python model.py > log 2>&1 &'''
import argparse
parser = argparse.ArgumentParser()
parser.add_argument(
    '--mode', type=str, default='evaluate',
    help='train/evaluate')
parser.add_argument(  #
    '--model_dir', type=str, default='hdfs://your_path/model',
    help='Base directory for the model.')
parser.add_argument(
    '--train_epochs', type=int, default=10, help='Number of training epochs.')
parser.add_argument(
    '--batch_size', type=int, default=1024, help='Number of examples per batch.')
parser.add_argument(
    '--train_data', type=str, default="hdfs://your_path//train/part*",
    help='Path to the training data.')
parser.add_argument(
    '--test_data', type=str, default='hdfs://your_path/test/part*',
    help='Path to the test data.')
parser.add_argument(
    '--servable_model_dir', type=str, default='hdfs://your_path/exported',
    help='Base directory for the eported model.')
parser.add_argument(
    '--profile_dir', type=str, default='hdfs://your_path/profile',
    help='Base directory for the eported model.')
parser.add_argument(
    '--is_profile', type=bool, default=False, help='if true ,open profile')

def model_fn(features,
             labels,
             mode,
             params):
  '''model_fn'''
  esmm_model = esmm(features,labels,params,mode)
  estimator_spec = esmm_model.Build_EstimatorSpec()
  return estimator_spec

def parse_tfrecords(rows_string_tensor):
  '''parse_tfrecords'''
  input_cols = get_input_schema_spec(input_schema)
  features = tf.parse_single_example(rows_string_tensor, input_cols)
  label_clcik = features.pop('click')
  label_buy = features.pop('buy')
  return features,tf.greater_equal(label_clcik,1),tf.greater_equal(label_buy,1)

def input_fn(filenames,
             num_epochs=None,
             shuffle=True,
             batch_size=200):
  '''input_fn'''
  files = tf.data.Dataset.list_files(filenames)
  assert files
  dataset = tf.data.TFRecordDataset(files,num_parallel_reads=6)
  if shuffle:
    dataset = dataset.shuffle(buffer_size=40000)

  dataset = dataset.map(parse_tfrecords, num_parallel_calls=6)#num_parallel_calls=tf.data.experimental.AUTOTUNE
  dataset = dataset.repeat(num_epochs)
  dataset = dataset.batch(batch_size)
  iterator = dataset.make_one_shot_iterator()
  features, label_click,label_buy = iterator.get_next()
  return features, {"ctr":tf.to_float(label_click),"cvr":tf.to_float(label_buy)}


input_schema = load_json_from_file("./model_schema.json")["schema"]
model_feature = load_json_from_file("./model_feature.json")
def main(unused_argv):

    _HIDDEN_UNITS = [200, 70, 50]
    _DNN_LEARNING_RATE = 0.002
    estimator_config = tf.estimator.RunConfig(
        save_checkpoints_secs=600, #save onetime per 300 secs
        keep_checkpoint_max=4 #save lastest 4 checkpoints
    )
    model = tf.estimator.Estimator(
        model_fn=model_fn,
        model_dir=FLAGS.model_dir,
        params={
            'HIDDEN_UNITS': _HIDDEN_UNITS,
            'LEARNING_RATE':_DNN_LEARNING_RATE,
            'FEATURES_DICT':model_feature
        },
        config= estimator_config)
    '''Generate Timeline'''
    timeline_hook =None
    if FLAGS.is_profile:
        timeline_hook = tf.train.ProfilerHook(save_steps=100000, output_dir=FLAGS.profile_dir, show_dataflow=True,
                                              show_memory=False)
    '''Train and Evaluate,Define train_spec and eval_spec '''
    train_spec = tf.estimator.TrainSpec(input_fn=lambda: input_fn(
        FLAGS.train_data, FLAGS.train_epochs, True, FLAGS.batch_size), hooks=[timeline_hook] if FLAGS.is_profile else None)
    eval_spec = tf.estimator.EvalSpec(input_fn=lambda: input_fn(
        FLAGS.test_data, 1, False, FLAGS.batch_size), steps=800,start_delay_secs=300, throttle_secs=300)
    '''Train and evaluate model'''
    results = tf.estimator.train_and_evaluate(model, train_spec, eval_spec)
    print(results)
    '''Export Trained Model for Serving'''
    export = export_model(model,input_schema,FLAGS.servable_model_dir,drop_cols=['label_click', 'label_buy'])
    flag = export.export()
    print(flag)
    print("*********** Finshed Total Pipeline ***********")

if __name__ == '__main__':
  tf.logging.set_verbosity(tf.logging.INFO)
  FLAGS, unparsed = parser.parse_known_args()
  tf.app.run(main=main, argv=[sys.argv[0]] + unparsed)


