FROM pegi3s/docker:20.04

RUN apt-get update -y && \
    apt-get install -y unzip
RUN apt-get install -y software-properties-common
RUN add-apt-repository ppa:deadsnakes/ppa
RUN apt-get update -y
RUN apt-get install -y python3
RUN apt-get install bc wget

COPY version1.zip /opt

WORKDIR /opt

RUN unzip version1.zip && \
    rm /opt/version1.zip

RUN chmod -R 777 /opt/*

CMD /opt/pre_main
