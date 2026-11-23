# auto-p2docking

This image facilitates the usage of **auto-p2docking**, a pipeline maker for protein-protein docking studies.

# Versions

## v1.0.0 - July 2024

An online manual is available [here](http://evolution6.i3s.up.pt/static/auto-p2docking/docs/).

# Using the auto-p2docking image in Linux

You should adapt and run the following command: `docker run --rm -v /your/data/dir:/data -v /var/run/docker.sock:/var/run/docker.sock pegi3s/auto-p2docking`

In this command, you should replace `/your/data/dir` to point to the directory that contains the input files of the pipeline. 

Please note that you must have a `pipeline` and a `config` file under `/your/data/dir` in order for the program to work. Detailed instructions are given in the online manual, where the available modules, as well as the parameters that must be declared for each module, are described in detail.

# Test data

## v1.0.0 - July 2024

Protocols are available that can be used both as inspiration to develop useful and efficient pipelines, as well as test data. By declaring in the first line of the pipeline file "protocol_description" a full list of the available protocols will be produced. By declaring the name of protocols (one per line, starting at the first line) in the pipeline file, the data for the corresponding protocol will be downloaded to the working directory.

