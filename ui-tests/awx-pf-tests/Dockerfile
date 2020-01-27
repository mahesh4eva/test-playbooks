FROM gcr.io/ansible-tower-engineering/awx_cypress_base:latest
RUN virtualenv -p python3.6 /venv-awxkit
RUN /venv-awxkit/bin/pip3.6 install nodeenv
RUN git clone https://github.com/ansible/awx
RUN venv-awxkit/bin/pip3.6 install -r awx/awxkit/requirements.txt
RUN cd awx && /venv-awxkit/bin/pip3.6 install -e ./awxkit[crypto]
ENTRYPOINT ["/bin/bash", "-c", "source /venv-awxkit/bin/activate && npm install && ${COMMAND} run"]
