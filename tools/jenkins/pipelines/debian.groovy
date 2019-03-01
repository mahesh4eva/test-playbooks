pipeline {

    agent none

    parameters {
        choice(
            name: 'TOWER_VERSION',
            description: 'Tower version to deploy',
            choices: ['devel', '3.4.2', '3.3.5', '3.2.9']
        )
        choice(
            name: 'SCOPE',
            description: 'What is the scope of the verification? (Full will run all supported permutation, latest only on latest OSes)',
            choices: ['latest', 'full']
        )
    }

    stages {

        stage('Build DEB') {
            steps {
                script {
                    if (params.TOWER_VERSION == 'devel') {
                        branch_name = 'devel'
                    } else {
                        branch_name = "release_${params.TOWER_VERSION}"
                    }
                }
                build(
                    job: 'Build_Tower_DEB',
                    parameters: [
                       string(name: 'TOWER_PACKAGING_BRANCH', value: "origin/${branch_name}"),
                       string(name: 'DEB_DIST', value: 'xenial'),
                       booleanParam(name: 'TRIGGER', value: false)
                    ]
                )
                script {
                    if (params.TOWER_VERSION in ['3.3.5', '3.2.9']) {
                        build(
                            job: 'Build_Tower_DEB',
                            parameters: [
                                string(name: 'TOWER_PACKAGING_BRANCH', value: "origin/${branch_name}"),
                                string(name: 'DEB_DIST', value: 'trusty'),
                                booleanParam(name: 'TRIGGER', value: false)
                            ]
                        )
                    }
                }
            }
        }

        stage('Operating System') {
            steps {
                script {
                    def tasks = [:]
                    def oses = [:]


                    if (params.SCOPE == 'latest' || params.TOWER_VERSION !=~ /3\.[0-3]*\.[0-9]*/) {
                        oses = ['ubuntu-16.04-x86_64']
                    } else {
                        oses = ['ubuntu-14.04-x86_64', 'ubuntu-16.04-x86_64']
                    }

                    for (int i=0;i<oses.size(); i++) {
                         def os = oses[i]

                         tasks[os] = {
                            build(
                                job: 'dispatch-pipeline',
                                parameters: [
                                    string(name: 'TOWER_VERSION', value: params.TOWER_VERSION),
                                    string(name: 'PLATFORM', value: os)
                                ]
                            )
                         }
                    }

                    stage('Operating System') {
                        parallel tasks
                    }
                }
            }
        }
    }
}
