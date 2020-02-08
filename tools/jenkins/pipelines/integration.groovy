pipeline {

    agent { label 'jenkins-jnlp-agent' }

    parameters {
        choice(
            name: 'TOWER_VERSION',
            description: 'Tower version to deploy',
            choices: ['devel', '3.6.3', '3.6.2', '3.6.1', '3.6.0',
                      '3.5.5', '3.5.4', '3.5.3', '3.5.2', '3.5.1', '3.5.0',
                      '3.4.6', '3.4.5', '3.4.4', '3.4.3', '3.4.2', '3.4.1', '3.4.0',
                      '3.3.8', '3.3.7', '3.3.6', '3.3.5', '3.3.4', '3.3.3', '3.3.2', '3.3.1', '3.3.0']
        )
        choice(
            name: 'ANSIBLE_VERSION',
            description: 'Ansible version to deploy within Tower install',
            choices: ['devel', 'stable-2.9', 'stable-2.8', 'stable-2.7', 'stable-2.6', 'stable-2.5',
                      'stable-2.4', 'stable-2.3']
        )
        choice(
            name: 'SCENARIO',
            description: 'Deployment scenario for Tower install',
            choices: ['standalone', 'cluster']
        )
        choice(
            name: 'AWX_USE_TLS',
            description: 'Should the network services (postgresql, rabbitmq and nginx) use TLS (with custom CA issued certificates)',
            choices: ['no', 'yes']
        )
        choice(
            name: 'AWX_USE_FIPS',
            description: 'Should FIPS be enabled for this deployment ?',
            choices: ['no', 'yes']
        )
        choice(
            name: 'PLATFORM',
            description: 'The OS to install the Tower instance on',
            choices: ['rhel-7.7-x86_64', 'rhel-7.6-x86_64', 'rhel-7.5-x86_64', 'rhel-7.4-x86_64',
                      'rhel-8.1-x86_64', 'rhel-8.0-x86_64', 'centos-7.latest-x86_64',
                      'ubuntu-16.04-x86_64', 'ubuntu-14.04-x86_64']
        )
        choice(
            name: 'BUNDLE',
            description: 'Should the bundle version be used ?',
            choices: ['no', 'yes']
        )
        choice(
            name: 'AWX_IPV6_DEPLOYMENT',
            description: 'Should the deployment use IPv6 ?',
            choices: ['no', 'yes']
        )
        string(
            name: 'TESTEXPR',
            description: 'Specify the TESTEXPR to pass to pytest if necessary',
            defaultValue: ''
        )
        string(
            name: 'TOWERQA_BRANCH',
            description: 'ansible/tower-qa branch to use (Empty will do the right thing)',
            defaultValue: ''
        )
        string(
            name: 'DEPLOYMENT_NAME',
            description: 'Deployment name. Will match VM name being spawned in the cloud',
            defaultValue: 'evergreen-jenkins-tower-integration'
        )
        choice(
            name: 'VERBOSE',
            description: 'Should the deployment be verbose ?',
            choices: ['no', 'yes']
        )
        choice(
            name: 'OUT_OF_BOX_OS',
            description: 'Should the deployment be made on a vanilla OS (ie. no prev preparation will take place) ?',
            choices: ['no', 'yes']
        )
        choice(
            name: 'FROM_STAGE',
            description: 'Should the installs and RPM be pulled from staging environment ?',
            choices: ['no', 'yes']
        )
        choice(
            name: 'CLEAN_DEPLOYMENT_BEFORE_JOB_RUN',
            description: 'Should the deployment be cleaned before job is run ?',
            choices: ['yes', 'no']
        )
        choice(
            name: 'CLEAN_DEPLOYMENT_AFTER_JOB_RUN',
            description: 'Should the deployment be cleaned after job is run ?',
            choices: ['yes', 'no']
        )
        choice(
            name: 'CLEAN_DEPLOYMENT_ON_JOB_FAILURE',
            description: 'Should the deployment be cleaned if job fails ?',
            choices: ['yes', 'no']
        )
        string(
            name: 'PG_HOST',
            description: 'Provide a database host. If none provided, the database will be installed on standalone or on its own ec2 host for cluster.',
            defaultValue: ''
        )
        string(
            name: 'PG_PORT',
            description: 'Provide the database port if using pre-configured database with PG_HOST',
            defaultValue: ''
        )
        string(
            name: 'PG_DATABASE',
            description: 'Provide the name of the database in the postgres instance if using pre-configured database with PG_HOST',
            defaultValue: ''
        )
        string(
            name: 'PG_USERNAME',
            description: 'Override default database user. If nothing provided, default will be used.',
            defaultValue: ''
        )
        string(
            name: 'PG_PASSWORD',
            description: 'Override default database user password. If nothing provided, default will be used.',
            defaultValue: ''
        )
        choice(
            name: 'CREATE_POLARION_TEST_RUN',
            description: 'Should the test results be uploaded to Polarion as a new Test Run?',
            choices: ['no', 'yes (production)', 'yes (stage)']
        )
        choice(
            name: 'UPDATE_QE_DASHBOARD',
            description: 'Should the results of this run be sent to the QE dashboard ?',
            choices: ['no', 'yes']
        )
    }

    options {
        timestamps()
        timeout(time: 18, unit: 'HOURS')
        buildDiscarder(logRotator(daysToKeepStr: '10'))
    }

    stages {

        stage('Build Information') {
            steps {
                echo """Tower Version under test: ${params.TOWER_VERSION}
Ansible Version under test: ${params.ANSIBLE_VERSION}
Platform under test: ${params.PLATFORM}
Scenario: ${params.SCENARIO}
Bundle?: ${params.BUNDLE}"""
            }
        }

        stage('Checkout tower-qa') {
            steps {
                script {
                    if (params.TOWER_VERSION == 'devel') {
                        tower_branch_name = 'devel'
                    } else {
                        tower_branch_name = "release_${params.TOWER_VERSION}"
                    }
                    if (params.TOWERQA_BRANCH == '') {
                        towerqa_branch_name = tower_branch_name
                    } else {
                        towerqa_branch_name = params.TOWERQA_BRANCH
                    }
                }
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: "*/${towerqa_branch_name}" ]],
                    userRemoteConfigs: [
                        [
                            credentialsId: 'github-ansible-jenkins-nopassphrase',
                            url: 'git@github.com:ansible/tower-qa.git'
                        ]
                    ]
                ])
            }
        }

        stage('Deploy test-runner node') {
            steps {
                withCredentials([file(credentialsId: '171764d8-e57c-4332-bff8-453670d0d99f', variable: 'PUBLIC_KEY'),
                                 file(credentialsId: 'abcd0260-fb83-404e-860f-f9697911a0bc', variable: 'VAULT_FILE'),
                                 file(credentialsId: '86ed99e9-dad9-49e9-b0db-9257fb563bad', variable: 'JSON_KEY_FILE'),
                                 string(credentialsId: 'aws_access_key', variable: 'AWS_ACCESS_KEY'),
                                 string(credentialsId: 'aws_secret_key', variable: 'AWS_SECRET_KEY'),
                                 string(credentialsId: 'awx_admin_password', variable: 'AWX_ADMIN_PASSWORD')]) {
                    withEnv(["AWS_SECRET_KEY=${AWS_SECRET_KEY}",
                             "AWS_ACCESS_KEY=${AWS_ACCESS_KEY}",
                             "AWX_USE_TLS=${AWX_USE_TLS}",
                             "AWX_USE_FIPS=${AWX_USE_FIPS}",
                             "AWX_ADMIN_PASSWORD=${AWX_ADMIN_PASSWORD}",
                             "PG_PASSWORD=${PG_PASSWORD}",
                             "PG_HOST=${PG_HOST}",
                             "PG_USERNAME=${PG_USERNAME}",
                             "PG_DATABASE=${PG_DATABASE}",
                             "PG_PORT=${PG_PORT}",
                             "ANSIBLE_FORCE_COLOR=true"]) {
                        sshagent(credentials : ['github-ansible-jenkins-nopassphrase']) {
                            sh './tools/jenkins/scripts/prep_test_runner.sh'
                            sh "ansible test-runner -i playbooks/inventory.test_runner -m git -a 'repo=git@github.com:ansible/tower-qa version=${towerqa_branch_name} dest=tower-qa ssh_opts=\"-o StrictHostKeyChecking=no\" force=yes'"
                        }
                    }
                }

                script {
                    TEST_RUNNER_HOST = readFile('artifacts/test_runner_host').trim()
                    SSH_OPTS = '-o ForwardAgent=yes -o StrictHostKeyChecking=no'
                }
            }
        }

        stage ('Install') {
            steps {
                withEnv(["PG_PASSWORD=${PG_PASSWORD}",
                         "PG_HOST=${PG_HOST}",
                         "PG_USERNAME=${PG_USERNAME}",
                         "PG_DATABASE=${PG_DATABASE}",
                         "PG_PORT=${PG_PORT}",
                         "ANSIBLE_FORCE_COLOR=true"]) {
                    sshagent(credentials : ['github-ansible-jenkins-nopassphrase']) {
                        sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && ./tools/jenkins/scripts/install.sh'"
                        sh "ansible test-runner -i playbooks/inventory.test_runner -a 'sed -i \"s/delete_on_start: .*/delete_on_start: false/g\" /home/ec2-user/tower-qa/playbooks/vars.yml'"
                    }
                }
            }
        }

        stage ('Install Idempotence') {
            steps {
                withEnv(["PG_PASSWORD=${PG_PASSWORD}",
                         "PG_HOST=${PG_HOST}",
                         "PG_USERNAME=${PG_USERNAME}",
                         "PG_DATABASE=${PG_DATABASE}",
                         "PG_PORT=${PG_PORT}",
                         "ANSIBLE_FORCE_COLOR=true"]) {
                    sshagent(credentials : ['github-ansible-jenkins-nopassphrase']) {
                        sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && ./tools/jenkins/scripts/install.sh'"
                    }
                }
            }
        }

        stage ('Integration Tests') {
            steps {
                withEnv(["TESTEXPR=${TESTEXPR}"]) {
                    sshagent(credentials : ['github-ansible-jenkins-nopassphrase']) {
                        sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && TESTEXPR=\"${params.TESTEXPR}\" ./tools/jenkins/scripts/test.sh'"
                        sh 'ansible-playbook -v -i playbooks/inventory.test_runner playbooks/test_runner/run_fetch_artifacts_test.yml'
                        junit 'artifacts/results.xml'
                    }
                }
            }
        }
        stage('Run CLI Tests') {
            steps {
                withEnv(["TESTEXPR=${TESTEXPR}"]) {
                    sshagent(credentials : ['github-ansible-jenkins-nopassphrase']) {
                        sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && TESTEXPR=\"${params.TESTEXPR}\" TOWER_BRANCH=\"${tower_branch_name}\" PRODUCT=\"tower\" ./tools/jenkins/scripts/test-cli.sh'"
                        sh 'ansible-playbook -v -i playbooks/inventory.test_runner playbooks/test_runner/run_fetch_artifacts_test_cli.yml'
                        junit 'artifacts/results-cli.xml'
                    }
                }
            }
        }
        stage('Run Collection Tests') {
            steps {
                sshagent(credentials : ['github-ansible-jenkins-nopassphrase']) {
                    sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && TESTEXPR=\"${params.TESTEXPR}\" TOWER_BRANCH=\"${tower_branch_name}\" PRODUCT=\"tower\" ./tools/jenkins/scripts/test-collection.sh'"
                    sh 'ansible-playbook -v -i playbooks/inventory.test_runner playbooks/test_runner/run_fetch_artifacts_test_collection.yml'
                    junit allowEmptyResults: true, testResults: 'artifacts/results-collection.xml'
                }
            }
        }
        stage('Collect artifacts (SOS Reports, pip freeze) from Tower instances') {
            steps {
                sshagent(credentials : ['github-ansible-jenkins-nopassphrase']) {
                    sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && ./tools/jenkins/scripts/collect.sh'"
                    sh 'ansible-playbook -v -i playbooks/inventory.test_runner playbooks/test_runner/run_fetch_artifacts_tower.yml'
                }
            }
        }

        stage('Create Polarion Test Run') {
            when {
                expression {
                    params.CREATE_POLARION_TEST_RUN.startsWith('yes')
                }
            }
            steps {
                script {
                    test_run_ansible_version = params.ANSIBLE_VERSION
                    test_run_bundle = 'false'
                    test_run_cluster = 'false'
                    test_run_os = params.PLATFORM
                    test_run_tower_version = params.TOWER_VERSION

                    if (params.BUNDLE == 'yes') {
                        test_run_bundle = 'true'
                    }
                    if (params.SCENARIO == 'cluster') {
                        test_run_cluster = 'true'
                    }
                    if (params.CREATE_POLARION_TEST_RUN.contains('production')) {
                        polarion_url = 'https://polarion.engineering.redhat.com'
                    } else {
                        polarion_url = 'https://polarion.stage.engineering.redhat.com'
                    }
                }

                withEnv([
                    "JUNIT_PATH=test-run-results.xml",
                    "POLARION_PASSWORD=polarion",
                    "POLARION_USERNAME=ansible_machine",
                    "POLARION_URL=${polarion_url}",
                    "TEST_RUN_ANSIBLEVERSION=${test_run_ansible_version}",
                    "TEST_RUN_BUNDLE=${test_run_bundle}",
                    "TEST_RUN_CLUSTER=${test_run_cluster}",
                    "TEST_RUN_OS=${test_run_os}",
                    "TEST_RUN_TOWERVERSION=${test_run_tower_version}"
                ]) {
                    sh './tools/jenkins/scripts/create-polarion-test-run.sh'
                }
            }
        }
    }

    post {
        always {
            sshagent(credentials : ['github-ansible-jenkins-nopassphrase']) {
                sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && ./tools/jenkins/scripts/collect.sh' || true"
                sh 'ansible-playbook -v -i playbooks/inventory.test_runner playbooks/test_runner/run_fetch_artifacts_tower.yml || true'
                sh 'ansible-playbook -v -i playbooks/inventory.test_runner playbooks/test_runner/run_fetch_artifacts.yml'
            }
            archiveArtifacts allowEmptyArchive: true, artifacts: 'artifacts/*'
            logstashSend failBuild: false, maxLines: 0
            node('jenkins-jnlp-agent') {
                withCredentials([string(credentialsId: 'jenkins_username', variable: 'JENKINS_USERNAME'),
                                    string(credentialsId: 'jenkins_token', variable: 'JENKINS_TOKEN')]) {
                    withEnv(["JENKINS_URL=http://jenkins.ansible.eng.rdu2.redhat.com",
                                "JENKINS_USERNAME=${JENKINS_USERNAME}",
                                "JENKINS_TOKEN=${JENKINS_TOKEN}",
                                "TOWER_VERSION=${params.TOWER_VERSION}",
                                "PLATFORM=${params.PLATFORM}",
                                "DEPLOY=${params.SCENARIO}",
                                "BUNDLE=${params.BUNDLE}",
                                "TLS=${params.AWX_USE_TLS}",
                                "FIPS=${params.AWX_USE_FIPS}",
                                "ANSIBLE=${params.ANSIBLE_VERSION}",
                                "STATUS=${currentBuild.result}",
                                "RUN_DISPLAY_URL=${env.RUN_DISPLAY_URL}",
                                "JOB_NAME=Pipelines/openshift-integration-pipeline",
                                "BUILD_ID=${currentBuild.id}"
                                ]) {
                        script {
                            sign_off_jobs = "{\"tower\":\"${params.TOWER_VERSION}\", \"bundle\":\"${params.BUNDLE}\", \"url\": \"${env.RUN_DISPLAY_URL}\", \"component\":\"integration\", \"status\":\"${currentBuild.result}\", \"tls\":\"${params.AWX_USE_TLS}\", \"fips\":\"${params.AWX_USE_FIPS}\", \"deploy\":\"${params.SCENARIO}\", \"platform\":\"${params.PLATFORM}\", \"ansible\":\"${params.ANSIBLE_VERSION}\"}"
                            content = sh(
                                script: "python tools/jenkins/scripts/test_result_json.py",
                                returnStdout: true
                            )
                            failed_tests = "${content}"
                        }
                        sh "test ${params.UPDATE_QE_DASHBOARD} = 'yes' && curl -v -X POST 'http://tower-qe-dashboard.ansible.eng.rdu2.redhat.com/jenkins/sign_off_jobs' -H 'Content-type: application/json' -d '${sign_off_jobs}' || echo 'Not updating dashboard for this run'"
                        sh "test ${params.UPDATE_QE_DASHBOARD} = 'yes' && curl -v -X POST 'http://tower-qe-dashboard.ansible.eng.rdu2.redhat.com/jenkins/integration_tests' -H 'Content-type: application/json' -d '${failed_tests}' || echo 'Not updating dashboard for this run'"
                    }
                }
            }
        }

        cleanup {
            script {
                if (params.CLEAN_DEPLOYMENT_AFTER_JOB_RUN == 'yes') {
                    sshagent(credentials : ['github-ansible-jenkins-nopassphrase']) {
                        sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && ./tools/jenkins/scripts/cleanup.sh'"
                    }
                }
            }
        }

        failure {
            script {
                if (params.CLEAN_DEPLOYMENT_ON_JOB_FAILURE == 'yes') {
                    sshagent(credentials : ['github-ansible-jenkins-nopassphrase']) {
                        sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && ./tools/jenkins/scripts/cleanup.sh'"
                    }
                }
            }
        }

    }
}
