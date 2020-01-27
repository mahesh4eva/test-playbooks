pipeline {
    agent {

            label 'jenkins-jnlp-agent'
    }
    parameters {
        string(
            name: 'AWX_E2E_URL',
            description: 'dont include https:// or trailing slashes',
            defaultValue: 'ec2-100-24-21-207.compute-1.amazonaws.com'
        )
        string(
            name: 'AWX_E2E_USERNAME',
            description: '',
            defaultValue: 'admin'
        )
        password(
            name: 'AWX_E2E_PASSWORD',
            description: 'Ignore to use default password',
        )
        string(
            name: 'UI_REPO',
            description: 'Points to the repo that contains the awx-pf UI code. Use git protocol format.',
            defaultValue: 'git@github.com:ansible/awx.git'
        )
        string(
            name: 'UI_BRANCH',
            description: 'Default is devel',
            defaultValue: 'devel'
        )
        string(
            name: 'E2E_TEST_REPO',
            description: 'Points to the tower-qa repo that contains the tests',
            defaultValue: 'git@github.com:ansible/tower-qa.git'
        )
        string(
            name: 'E2E_TEST_BRANCH',
            description: 'Default is devel',
            defaultValue: 'devel'
        )
        string(
            name: 'SLACK_CHANNEL',
            description: 'Can be either a #channel or @user',
            defaultValue: '#e2e-test-results'
        )
        booleanParam(
            name: 'UPLOAD_SNAPSHOTS_TO_PERCY',
            description: 'If checked, Snapshots will be captured and uploaded to Percy for Visual Regression Testing',
            defaultValue: false
        )
    }
    options {
        timeout(time: 2, unit: 'HOURS')
        timestamps()
        ansiColor('xterm')
        parallelsAlwaysFailFast()
        buildDiscarder(logRotator(daysToKeepStr: '10'))
    }
    stages {
        stage ('Clone Git repo') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [
                        [ name: "${E2E_TEST_BRANCH}" ]
                    ],
                    doGenerateSubmoduleConfigurations: false,
                    extensions: [[
                        $class: 'RelativeTargetDirectory', 
                        relativeTargetDir: 'tower-qa'
                    ]], 
                    submoduleCfg: [],
                    userRemoteConfigs: [
                        [
                            credentialsId: 'github-ansible-jenkins-nopassphrase',
                            url: '${E2E_TEST_REPO}'
                        ]
                    ]
                ])
                checkout([
                    $class: 'GitSCM',
                    branches: [
                        [ name: "${UI_BRANCH}" ]
                    ],
                    doGenerateSubmoduleConfigurations: false,
                    extensions: [[
                        $class: 'RelativeTargetDirectory', 
                        relativeTargetDir: 'awx'
                    ]], 
                    submoduleCfg: [],
                    userRemoteConfigs: [
                        [
                            credentialsId: 'github-ansible-jenkins-nopassphrase',
                            url: '${UI_REPO}'
                        ]
                    ]
                ])
            }
        }
        stage ('Apply license') {
            steps {
                withCredentials([file(credentialsId: '86ed99e9-dad9-49e9-b0db-9257fb563bad', variable: 'JSON_KEY_FILE_PATH')]) {
                sshagent(['github-ansible-jenkins-nopassphrase']) {
                    sh '''#!/bin/bash -e
                    set +x
                    python "tower-qa/tools/jenkins/scripts/apply_license_py2.py" -u "${AWX_E2E_USERNAME}" -p "${AWX_E2E_PASSWORD}" https://"${AWX_E2E_URL}"
                    set -x
                    '''
                }}
            }
        }
        stage ('Allow remote UI connections') {
            steps {
                sshagent(credentials : ['github-ansible-jenkins-nopassphrase']) {
                sh '''#!/bin/sh
                     
                     # Ansible ad-hoc command to modify /etc/tower/settings.py to allow remote UI calls.
                     ansible all -i "${AWX_E2E_URL}," -m lineinfile -a 'path=/etc/tower/settings.py line=\"CSRF_TRUSTED_ORIGINS=['\\''{{ lookup("env", "AWX_E2E_URL") }}:443'\\'']\" state=present' --ssh-extra-args='-o "StrictHostKeyChecking no"' --become --become-user=root -u 'ec2-user'
                     # Ansible ad-hoc command to restart tower and refresh settings.py
                     ansible all -i "${AWX_E2E_URL}," -m shell -a 'systemctl restart ansible-tower' --become --become-user=root -u 'ec2-user'
                     '''
                }
           }
        }
        stage('Start awx-pf locally') {
          steps {
                withCredentials([file(credentialsId: '86ed99e9-dad9-49e9-b0db-9257fb563bad', variable: 'JSON_KEY_FILE_PATH'),
                                string(credentialsId: 'PERCY_TOKEN_APURVA', variable: 'PERCY_TOKEN')]) {
                    sshagent(['github-ansible-jenkins-nopassphrase']) {
                        sh '''#!/bin/bash -xe
                        #set remote target
                        export TARGET_HOST="${AWX_E2E_URL}"
                        export TARGET_PORT='443'

                        set +x
                        docker login -u _json_key -p "$(cat "${JSON_KEY_FILE_PATH}")" https://gcr.io
                        set -x

                        cd awx/awx/ui_next
                        docker build -t awx-ui-next .
                        docker run --name 'ui-next' --network='default' -e TARGET_PORT='443' -e TARGET_HOST="${AWX_E2E_URL}" -p '3001:3001' -d -v $(pwd)/src:/ui_next/src awx-ui-next
                        sleep 10
                        if [ params.UPLOAD_SNAPSHOTS_TO_PERCY ]
                        then
                            cd ../../../tower-qa/ui-tests/awx-pf-tests
                            docker build -t awx-pf-tests .
                            docker run -e PERCY_TOKEN="${PERCY_TOKEN}" -e COMMAND="percy" -e CYPRESS_AWX_E2E_USERNAME="${AWX_E2E_USERNAME}" -e CYPRESS_AWX_E2E_PASSWORD="${AWX_E2E_PASSWORD}" --network 'default' --link 'ui-next:ui-next' -v $PWD:/e2e -w /e2e awx-pf-tests run --project .
                        else
                            cd ../../../tower-qa/ui-tests/awx-pf-tests
                            docker build -t awx-pf-tests .
                            docker run -e CYPRESS_AWX_E2E_USERNAME="${AWX_E2E_USERNAME}" -e COMMAND="cypress" -e CYPRESS_AWX_E2E_PASSWORD="${AWX_E2E_PASSWORD}" --network 'default' --link 'ui-next:ui-next' -v $PWD:/e2e -w /e2e awx-pf-tests run --project .

                        '''
                    }
                }
            }
        }
    }
    post {
        always {
            xunit thresholds: [
                    failed(failureThreshold: '2', 
                    unstableThreshold: '1')
                ], 
                tools: [
                    Custom(customXSL: 'tower-qa/ui-tests/awx-pf-tests/cypress-report-stylesheet.xsl', 
                    deleteOutputFiles: true, 
                    failIfNotNew: true, 
                    pattern: 'tower-qa/ui-tests/awx-pf-tests/results/*.xml', 
                    skipNoTestFiles: false, stopProcessingIfError: true)
                ]
        }
        success {
            slackSend(
                teamDomain: "ansible",
                channel: "${SLACK_CHANNEL}",
                message: "patternfly ${UI_BRANCH} branch pipeline is <${env.RUN_DISPLAY_URL}|passing>"
            )
        }
        unstable {
            slackSend(
                teamDomain: "ansible",
                channel: "${SLACK_CHANNEL}",
                message: "patternfly ${UI_BRANCH} branch pipeline is <${env.RUN_DISPLAY_URL}|unstable>"
            )
        }
        failure {
            slackSend(
                teamDomain: "ansible",
                channel: "${SLACK_CHANNEL}",
                message: "patternfly ${UI_BRANCH} branch pipeline is <${env.RUN_DISPLAY_URL}|failing>"
            )
        }
    }
}


