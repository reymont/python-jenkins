#!/usr/bin/env python
# Software License Agreement (BSD License)
#
# Copyright (c) 2010, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# 'AS IS' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Authors:
# Ken Conley <kwc@willowgarage.com>
# James Page <james.page@canonical.com>
# Tully Foote <tfoote@willowgarage.com>
# Matthew Gertner <matthew.gertner@gmail.com>

'''
Python API for Jenkins

Examples::

    j = jenkins.Jenkins('http://your_url_here', 'username', 'password')
    j.get_jobs()
    j.create_job('empty', jenkins.EMPTY_CONFIG_XML)
    j.disable_job('empty')
    j.copy_job('empty', 'empty_copy')
    j.enable_job('empty_copy')
    j.reconfig_job('empty_copy', jenkins.RECONFIG_XML)

    j.delete_job('empty')
    j.delete_job('empty_copy')

    # build a parameterized job
    j.build_job('api-test', {'param1': 'test value 1', 'param2': 'test value 2'})
'''

import sys
import urllib2
import urllib
import base64
import traceback
import json
import httplib

INFO         = 'api/json'
JOB_INFO     = 'job/%(name)s/api/json?depth=0'
Q_INFO       = 'queue/api/json?depth=0'
CREATE_JOB   = 'createItem?name=%(name)s' #also post config.xml
CONFIG_JOB   = 'job/%(name)s/config.xml'
DELETE_JOB   = 'job/%(name)s/doDelete'
ENABLE_JOB   = 'job/%(name)s/enable'
DISABLE_JOB  = 'job/%(name)s/disable'
COPY_JOB     = 'createItem?name=%(to_name)s&mode=copy&from=%(from_name)s'
BUILD_JOB    = 'job/%(name)s/build'
BUILD_WITH_PARAMS_JOB = 'job/%(name)s/buildWithParameters'
BUILD_INFO   = 'job/%(name)s/%(number)d/api/json?depth=0'


CREATE_NODE = 'computer/doCreateItem?%s'
DELETE_NODE = 'computer/%(name)s/doDelete'
NODE_INFO   = 'computer/%(name)s/api/json?depth=0'
NODE_TYPE   = 'hudson.slaves.DumbSlave$DescriptorImpl'


#for testing only
EMPTY_CONFIG_XML = '''<?xml version='1.0' encoding='UTF-8'?>
<project>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <scm class='jenkins.scm.NullSCM'/>
  <canRoam>true</canRoam>
  <disabled>false</disabled>
  <blockBuildWhenUpstreamBuilding>false</blockBuildWhenUpstreamBuilding>
  <triggers class='vector'/>
  <concurrentBuild>false</concurrentBuild>
  <builders/>
  <publishers/>
  <buildWrappers/>
</project>'''

#for testing only
RECONFIG_XML = '''<?xml version='1.0' encoding='UTF-8'?>
<project>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <scm class='jenkins.scm.NullSCM'/>
  <canRoam>true</canRoam>
  <disabled>false</disabled>
  <blockBuildWhenUpstreamBuilding>false</blockBuildWhenUpstreamBuilding>
  <triggers class='vector'/>
  <concurrentBuild>false</concurrentBuild>
<builders> 
    <jenkins.tasks.Shell> 
      <command>export FOO=bar</command> 
    </jenkins.tasks.Shell> 
  </builders> 
  <publishers/>
  <buildWrappers/>
</project>'''

class JenkinsException(Exception):
    '''
    General exception type for jenkins-API-related failures.
    '''
    pass

def auth_headers(username, password):
    '''
    Simple implementation of HTTP Basic Authentication. Returns the 'Authentication' header value.
    '''
    return 'Basic ' + base64.encodestring('%s:%s' % (username, password))[:-1]

class Jenkins(object):

    def __init__(self, url, username=None, password=None):
        '''
        Create handle to Jenkins instance.

        :param url: URL of Jenkins server, ``str``
        '''
        if url[-1] == '/':
            self.server = url
        else:
            self.server = url + '/'
        if username is not None and password is not None:
            self.auth = auth_headers(username, password)
        else:
            self.auth = None

    def get_job_info(self, name):
        '''
        Get job information dictionary.

        :param name: Job name, ``str``
        :returns: dictionary of job information
        '''
        try:
            response = self.jenkins_open(urllib2.Request(self.server + JOB_INFO%locals()))
            if response:
                return json.loads(response)
            else:
                raise JenkinsException('job[%s] does not exist'%name)
        except urllib2.HTTPError:
            raise JenkinsException('job[%s] does not exist'%name)
        except ValueError:
            raise JenkinsException("Could not parse JSON info for job[%s]"%name)

    def debug_job_info(self, job_name):
        '''
        Print out job info in more readable format
        '''
        for k, v in self.get_job_info(job_name).iteritems():
            print k, v

    def jenkins_open(self, req):
        '''
        Utility routine for opening an HTTP request to a Jenkins server.   This should only be used
        to extends the :class:`Jenkins` API.
        '''
        try:
            if self.auth:
                req.add_header('Authorization', self.auth)
            return urllib2.urlopen(req).read()
        except urllib2.HTTPError, e:
            # Jenkins's funky authentication means its nigh impossible to distinguish errors.
            if e.code in [401, 403, 500]:
                raise JenkinsException('Error in request. Possibly authentication failed [%s]'%(e.code))
            # right now I'm getting 302 infinites on a successful delete

    def get_build_info(self, name, number):
        '''
        Get build information dictionary.

        :param name: Job name, ``str``
        :param name: Build number, ``int``
        :returns: dictionary of build information, ``dict``

        Example::

            >>> next_build_number = j.get_job_info('build_name')['next_build_number']
            >>> output = j.build_job('build_'+kwargs['vcs_server_type'], params)
            >>> sleep(10)
            >>> build_info = j.get_build_info('build_name', next_build_number)
            >>> print(build_info)
            {u'building': False, u'changeSet': {u'items': [{u'date': u'2011-12-19T18:01:52.540557Z', u'msg': u'test', u'revision': 66, u'user': u'unknown', u'paths': [{u'editType': u'edit', u'file': u'/branches/demo/index.html'}]}], u'kind': u'svn', u'revisions': [{u'module': u'http://eaas-svn01.i3.level3.com/eaas', u'revision': 66}]}, u'builtOn': u'', u'description': None, u'artifacts': [{u'relativePath': u'dist/eaas-87-2011-12-19_18-01-57.war', u'displayPath': u'eaas-87-2011-12-19_18-01-57.war', u'fileName': u'eaas-87-2011-12-19_18-01-57.war'}, {u'relativePath': u'dist/eaas-87-2011-12-19_18-01-57.war.zip', u'displayPath': u'eaas-87-2011-12-19_18-01-57.war.zip', u'fileName': u'eaas-87-2011-12-19_18-01-57.war.zip'}], u'timestamp': 1324317717000, u'number': 87, u'actions': [{u'parameters': [{u'name': u'SERVICE_NAME', u'value': u'eaas'}, {u'name': u'PROJECT_NAME', u'value': u'demo'}]}, {u'causes': [{u'userName': u'anonymous', u'shortDescription': u'Started by user anonymous'}]}, {}, {}, {}], u'id': u'2011-12-19_18-01-57', u'keepLog': False, u'url': u'http://eaas-jenkins01.i3.level3.com:9080/job/build_war/87/', u'culprits': [{u'absoluteUrl': u'http://eaas-jenkins01.i3.level3.com:9080/user/unknown', u'fullName': u'unknown'}], u'result': u'SUCCESS', u'duration': 8826, u'fullDisplayName': u'build_war #87'}
        '''
        try:
            response = self.jenkins_open(urllib2.Request(self.server + BUILD_INFO%locals()))
            if response:
                return json.loads(response)
            else:
                raise JenkinsException('job[%s] number[%d] does not exist'%(name, number))
        except urllib2.HTTPError:
            raise JenkinsException('job[%s] number[%d] does not exist'%(name, number))
        except ValueError:
            raise JenkinsException('Could not parse JSON info for job[%s] number[%d]'%(name, number))

    def get_queue_info(self):
        '''
        :returns: list of job dictionaries, ``[dict]``

        Example::
            >>> queue_info = j.get_queue_info()
            >>> print(queue_info[0])
            {u'task': {u'url': u'http://your_url/job/my_job/', u'color': u'aborted_anime', u'name': u'my_job'}, u'stuck': False, u'actions': [{u'causes': [{u'shortDescription': u'Started by timer'}]}], u'buildable': False, u'params': u'', u'buildableStartMilliseconds': 1315087293316, u'why': u'Build #2,532 is already in progress (ETA:10 min)', u'blocked': True}
        '''
        return json.loads(self.jenkins_open(urllib2.Request(self.server + Q_INFO)))['items']

    def get_info(self):
        """
        Get information on this Master.  This information
        includes job list and view information.

        :returns: dictionary of information about Master, ``dict``

        Example::

            >>> info = j.get_info()
            >>> jobs = info['jobs']
            >>> print(jobs[0])
            {u'url': u'http://your_url_here/job/my_job/', u'color': u'blue', u'name': u'my_job'}

        """
        try:
            return json.loads(self.jenkins_open(urllib2.Request(self.server + INFO)))
        except urllib2.HTTPError:
            raise JenkinsException("Error communicating with server[%s]"%self.server)
        except httplib.BadStatusLine:
            raise JenkinsException("Error communicating with server[%s]"%self.server)
        except ValueError:
            raise JenkinsException("Could not parse JSON info for server[%s]"%self.server)

    def get_jobs(self):
        """
        Get list of jobs running.  Each job is a dictionary with
        'name', 'url', and 'color' keys.

        :returns: list of jobs, ``[ { str: str} ]``
        """
        return self.get_info()['jobs']

    def copy_job(self, from_name, to_name):
        '''
        Copy a Jenkins job

        :param from_name: Name of Jenkins job to copy from, ``str``
        :param to_name: Name of Jenkins job to copy to, ``str``
        '''
        self.get_job_info(from_name)
        self.jenkins_open(urllib2.Request(self.server + COPY_JOB%locals(), ''))
        if not self.job_exists(to_name):
            raise JenkinsException('create[%s] failed'%(to_name))

    def delete_job(self, name):
        '''
        Delete Jenkins job permanently.
        
        :param name: Name of Jenkins job, ``str``
        '''
        self.get_job_info(name)
        self.jenkins_open(urllib2.Request(self.server + DELETE_JOB%locals(), ''))
        if self.job_exists(name):
            raise JenkinsException('delete[%s] failed'%(name))

    def enable_job(self, name):
        '''
        Enable Jenkins job.

        :param name: Name of Jenkins job, ``str``
        '''
        self.get_job_info(name)
        self.jenkins_open(urllib2.Request(self.server + ENABLE_JOB%locals(), ''))

    def disable_job(self, name):
        '''
        Disable Jenkins job. To re-enable, call :meth:`Jenkins.enable_job`.

        :param name: Name of Jenkins job, ``str``
        '''
        self.get_job_info(name)
        self.jenkins_open(urllib2.Request(self.server + DISABLE_JOB%locals(), ''))

    def job_exists(self, name):
        '''
        :param name: Name of Jenkins job, ``str``
        :returns: ``True`` if Jenkins job exists
        '''
        try:
            self.get_job_info(name)
            return True
        except JenkinsException:
            return False

    def create_job(self, name, config_xml):
        '''
        Create a new Jenkins job

        :param name: Name of Jenkins job, ``str``
        :param config_xml: config file text, ``str``
        '''
        if self.job_exists(name):
            raise JenkinsException('job[%s] already exists'%(name))

        headers = {'Content-Type': 'text/xml'}
        self.jenkins_open(urllib2.Request(self.server + CREATE_JOB%locals(), config_xml, headers))
        if not self.job_exists(name):
            raise JenkinsException('create[%s] failed'%(name))

    def get_job_config(self, name):
        '''
        Get configuration of existing Jenkins job.

        :param name: Name of Jenkins job, ``str``
        :returns: job configuration (XML format)
        '''
        get_config_url = self.server + CONFIG_JOB%locals()
        return self.jenkins_open(urllib2.Request(get_config_url))

    def reconfig_job(self, name, config_xml):
        '''
        Change configuration of existing Jenkins job.  To create a new job, see :meth:`Jenkins.create_job`.

        :param name: Name of Jenkins job, ``str``
        :param config_xml: New XML configuration, ``str``
        '''
        self.get_job_info(name)
        headers = {'Content-Type': 'text/xml'}
        reconfig_url = self.server + CONFIG_JOB%locals()
        self.jenkins_open(urllib2.Request(reconfig_url, config_xml, headers))

    def build_job_url(self, name, parameters=None, token=None):
        '''
        Get URL to trigger build job.  Authenticated setups may require configuring a token on the server side.
        
        :param parameters: parameters for job, or None., ``dict``
        :param token: (optional) token for building job, ``str``
        :returns: URL for building job
        '''
        if parameters:
            if token:
                parameters['token'] = token
            return self.server + BUILD_WITH_PARAMS_JOB%locals() + '?' + urllib.urlencode(parameters)
        elif token:
            return self.server + BUILD_JOB%locals() + '?' + urllib.urlencode({'token': token})
        else:
            return self.server + BUILD_JOB%locals()

    def build_job(self, name, parameters=None, token=None):
        '''
        Trigger build job.
        
        :param parameters: parameters for job, or ``None``, ``dict``
        '''
        if not self.job_exists(name):
            raise JenkinsException('no such job[%s]'%(name))
        return self.jenkins_open(urllib2.Request(self.build_job_url(name, parameters, token)))

    def get_node_info(self, name):
        '''
        Get node information dictionary

        :param name: Node name, ``str``
        :returns: Dictionary of node info, ``dict``
        '''
        try:
            response = self.jenkins_open(urllib2.Request(self.server + NODE_INFO%locals()))
            if response:
                return json.loads(response)
            else:
                raise JenkinsException('node[%s] does not exist'%name)
        except urllib2.HTTPError:
            raise JenkinsException('node[%s] does not exist'%name)
        except ValueError:
            raise JenkinsException("Could not parse JSON info for node[%s]"%name)

    def node_exists(self, name):
        '''
        :param name: Name of Jenkins node, ``str``
        :returns: ``True`` if Jenkins node exists
        '''
        try:
            self.get_node_info(name)
            return True
        except JenkinsException:
            return False

    def delete_node(self, name):
        '''
        Delete Jenkins node permanently.
        
        :param name: Name of Jenkins node, ``str``
        '''
        self.get_node_info(name)
        self.jenkins_open(urllib2.Request(self.server + DELETE_NODE%locals(), ''))
        if self.node_exists(name):
            raise JenkinsException('delete[%s] failed'%(name))


    def create_node(self, name, numExecutors=2, nodeDescription=None,
                    remoteFS='/var/lib/jenkins', labels=None, exclusive=False):
        '''
        :param name: name of node to create, ``str``
        :param numExecutors: number of executors for node, ``int``
        :param nodeDescription: Description of node, ``str``
        :param remoteFS: Remote filesystem location to use, ``str``
        :param labels: Labels to associate with node, ``str``
        :param exclusive: Use this node for tied jobs only, ``bool``
        '''
        if self.node_exists(name):
            raise JenkinsException('node[%s] already exists'%(name))

        mode = 'NORMAL'
        if exclusive:
            mode = 'EXCLUSIVE'

        params = {
            'name' : name,
            'type' : NODE_TYPE,
            'json' : json.dumps ({
                'name'            : name,
                'nodeDescription' : nodeDescription,
                'numExecutors'    : numExecutors,
                'remoteFS'        : remoteFS,
                'labelString'     : labels,
                'mode'            : mode,
                'type'            : NODE_TYPE,
                'retentionStrategy' : { 'stapler-class'  : 'hudson.slaves.RetentionStrategy$Always' },
                'nodeProperties'    : { 'stapler-class-bag' : 'true' },
                'launcher'          : { 'stapler-class' : 'hudson.slaves.JNLPLauncher' }
            })
        }

        self.jenkins_open(urllib2.Request(self.server + CREATE_NODE%urllib.urlencode(params)))
        if not self.node_exists(name):
            raise JenkinsException('create[%s] failed'%(name))