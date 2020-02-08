#!/usr/bin/env python

import os
from jenkinsapi.jenkins import Jenkins
import json

def main():
    jenkins_url = os.getenv('JENKINS_URL')
    jenkins_username = os.getenv('JENKINS_USERNAME')
    jenkins_token = os.getenv('JENKINS_TOKEN')
    job_name = os.getenv('JOB_NAME')

    tower = os.getenv('TOWER_VERSION')
    platform = os.getenv('PLATFORM')
    deploy = os.getenv('DEPLOY')
    bundle = os.getenv('BUNDLE')
    tls = os.getenv('TLS')
    fips = os.getenv('FIPS')
    ansible = os.getenv('ANSIBLE')
    status = os.getenv('STATUS')
    url = os.getenv('RUN_DISPLAY_URL')
    build_id = os.getenv('BUILD_ID')

    server = Jenkins(jenkins_url, username=jenkins_username, password=jenkins_token)
    job = server.get_job(job_name)
    build = job.get_build(build_id)
    test_results = build.get_resultset().__dict__['_data']['suites'][0]['cases']
    failed_tests = {}
    failed_tests['name'] = [d['name'] for d in test_results if d['status']=="FAILED" ]
    failed_tests.update([ ('tower', tower) , ('deploy', deploy) , ('platform' , platform) , ('bundle', bundle) , ('tls', tls) , ('fips', fips) , ('ansible', ansible) , ('status', status) , ('url', url)] )
    failed_tests = json.dumps(failed_tests)
    print(failed_tests)


if __name__ == "__main__":
    main()
