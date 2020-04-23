#!/usr/bin/env python2.7

import socket
import hashlib
import os
import stat
import shutil
import filecmp
import time

from kubernetes import client, config, watch
from jinja2 import Template

interface_prefix = 'cali'

runit_directory = '/etc/service'

zeek_spool_directory = '/zeek/spool'
zeek_path = '/zeek/bin/zeek'
zeek_args = ' -U zeek-status local.zeek zeekctl base/frameworks/cluster zeekctl/auto'

cluster_layout_file = '/zeek/spool/auto/cluster-layout.zeek'
cluster_layout_template_file = '/watch/templates/cluster-layout.zeek.j2'

##########

my_zeek_node_type = os.environ.get('ZEEK_NODE_TYPE').upper()
my_node_name = os.environ.get('NODE_NAME')

monitored_pods = {}
zeek_pods = {}

def monitor():
  global monitored_pods
  global zeek_pods

  print("Running on node %s as %s" % (my_node_name, my_zeek_node_type))

  config.load_incluster_config()

  v1 = client.CoreV1Api()
  w = watch.Watch()

  for event in w.stream(v1.list_pod_for_all_namespaces):
    event_type = event['type']
    labels = event['object'].metadata.labels
    metadata = event['object'].metadata
    key = metadata.namespace + '.' + metadata.name

    if event_type in ['ADDED', 'MODIFIED']:
      if 'zeek-monitor' in labels:
        monitored_pods[key] = event['object']
      if 'zeek-node' in labels:
        zeek_pods[key] = event['object']

    if event_type in ['DELETED']:
      if key in monitored_pods:
        del monitored_pods[key]
      if key in zeek_pods:
        del monitored_pods[key]

    zeek_topology = []
    zeek_workers = {}

    for key in zeek_pods.keys():
      pod = zeek_pods[key]
      pod_name = pod.metadata.name
      pod_ip = pod.status.pod_ip

      node_name = pod.spec.node_name

      zeek_node_type = pod.metadata.labels['zeek-node'].upper()

      if zeek_node_type in ['MANAGER']:
        zeek_node_name = 'manager'
        zeek_topology.append({ 'name': zeek_node_name, 'type': zeek_node_type, 'ip': pod_ip })
      if zeek_node_type in ['PROXY', 'LOGGER']:
        zeek_node_name = '%s-%s' % (node_type.lower(), pod_name)
        zeek_topology.append({ 'name': zeek_node_name, 'type': zeek_node_type, 'ip': pod_ip, 'manager': 'manager' })
      if zeek_node_type in ['WORKER']:
        zeek_workers[node_name] = pod

    for key in monitored_pods.keys():
      pod = monitored_pods[key]
      pod_name = pod.metadata.name
      pod_namespace = pod.metadata.namespace

      node_name = pod.spec.node_name

      if node_name in zeek_workers:
        zeek_worker_ip = zeek_workers[node_name].status.pod_ip   
        zeek_node_name = 'worker-%s-%s' % (pod_namespace, pod_name)
        interface_hash = hashlib.sha1('%s.%s' % (pod_namespace, pod_name))
        zeek_interface = '%s%s' % (interface_prefix, interface_hash.hexdigest()[:11])
        zeek_topology.append({ 'name': zeek_node_name, 'type': 'WORKER', 'ip': zeek_worker_ip, 'manager': 'manager', 'interface': zeek_interface })

    zeek_topology.sort(key = lambda e: e['name'])
    port = 47761

    for element in zeek_topology:
      element['port'] = port
      port += 1

    with open(cluster_layout_template_file) as fi:
      template = Template(fi.read())

      if not os.path.isfile(cluster_layout_file):
        with open(cluster_layout_file, 'w') as fo:
          fo.write(template.render(zeek_topology=zeek_topology))
        sync_zeek()
      else:
        cluster_layout_file_temp = cluster_layout_file + '.tmp'

        with open(cluster_layout_file_temp, 'w') as fo:
          fo.write(template.render(zeek_topology=zeek_topology))

        equal = filecmp.cmp(cluster_layout_file, cluster_layout_file_temp)

        if not equal:
          os.rename(cluster_layout_file_temp, cluster_layout_file)
          sync_zeek()

def sync_zeek():
  global monitored_pods

  for d in os.listdir(runit_directory):
    if d != 'watch':
      shutil.rmtree(os.path.join(runit_directory, d))

  time.sleep(6)

  if my_zeek_node_type in ['MANAGER', 'PROXY', 'LOGGER']:
    path = os.path.join(runit_directory, my_zeek_node_type.lower())

    if my_zeek_node_type in ['MANAGER']:
      zeek_node_name = 'manager'
    else:
      zeek_node_name = '%s-%s' % (node_type.lower(), pod_name)

    os.mkdir(path)

    run_path = os.path.join(path, 'run')  
    env_dir = os.path.join(path, 'env')
    spool_dir = os.path.join(zeek_spool_directory, zeek_node_name)
  
    os.mkdir(env_dir)

    if not os.path.isdir(spool_dir):
      os.mkdir(spool_dir)

    cluster_node_path = os.path.join(env_dir, 'CLUSTER_NODE')
 
    with open(cluster_node_path, 'w') as cluster_node:
      cluster_node.write(zeek_node_name)

    zeek = zeek_path + zeek_args
  
    chpst = '#!/bin/sh\ncd %s\nexec 2>&1 /usr/bin/chpst -e %s %s' % (spool_dir, env_dir, zeek)

    with open(run_path, 'w') as run:
      run.write(chpst)
  
    st = os.stat(run_path)
    os.chmod(run_path, st.st_mode | stat.S_IEXEC)
  else:
    my_monitored_pods = dict(filter(lambda e: e[1].spec.node_name == my_node_name, monitored_pods.items()))

    for key in my_monitored_pods.keys():
      path = os.path.join(runit_directory, key)
  
      pod = my_monitored_pods[key]
      pod_name = pod.metadata.name
      pod_namespace = pod.metadata.namespace
  
      zeek_node_name = 'worker-%s-%s' % (pod_namespace, pod_name)
  
      interface_hash = hashlib.sha1('%s.%s' % (pod_namespace, pod_name))
      zeek_interface = '%s%s' % (interface_prefix, interface_hash.hexdigest()[:11])
  
      os.mkdir(path)

      run_path = os.path.join(path, 'run')  
      env_dir = os.path.join(path, 'env')
      spool_dir = os.path.join(zeek_spool_directory, zeek_node_name)
  
      os.mkdir(env_dir)

      if not os.path.isdir(spool_dir):
        os.mkdir(spool_dir)

      cluster_node_path = os.path.join(env_dir, 'CLUSTER_NODE')
 
      with open(cluster_node_path, 'w') as cluster_node:
        cluster_node.write(zeek_node_name)
  
      zeek = zeek_path + zeek_args + ' -i ' + zeek_interface
  
      chpst = '#!/bin/sh\ncd %s\nexec 2>&1 /usr/bin/chpst -e %s %s' % (spool_dir, env_dir, zeek)
  
      with open(run_path, 'w') as run:
        run.write(chpst)
  
      st = os.stat(run_path)
      os.chmod(run_path, st.st_mode | stat.S_IEXEC)

def main():
  monitor()

if __name__ == '__main__':
  main()
