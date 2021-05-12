[![Build Status](https://tjek2.drecks-provider.de/badges/atx/Gierlappen2/status.svg)](https://tjek2.drecks-provider.de/repository/12)

# Gierlappen: fine-grained just-in-time defect prediction data mining

This is a research prototype for mining fine-grained just-in-time defect predicition data. It is designed to maximize available data by traversing all branches and keeping track of state for every file on every branch.
The memory consumption is currently prohibitive and it may run out of memory on large repositories with a large number of files.
This is a work in progress.

## Features
Some overview of avaliable features.

### State saving
Gierlappen is able to save the state of repository traversal in a state file.
This allows traversing and collecting data for a repository and later continue only the newest commits.
This feature is experimental and there are some open questions, e.g., if a bug is discovered later should we update previous bug-inducing labels? This is currently the case.

### Caching
As we perform some time-expensive operations, e.g., executing PMD or Pylint for every file in every commit we create sqlite databases for each repository in the cache folder. This allows us to quickly re-traverse a repository without having to collect this information again.

There is a Postgresql caching implementation available for static analysis warnings which is currently disabled.
If you need a Postgresql database instead of sqlite this can be re-enabled in connectors/pmd_db.py.
It requires the psycopg2 library.

### Fine-grained just-in-time and traditional just-in-time features
Currently, Gierlappen supports just-in-time defect prediction features by [Kamei et al.](https://ieeexplore.ieee.org/document/6341763) and fine-grained just-in-time defect prediction features by [Pascarella et al.](https://www.lucapascarella.com/articles/2018/Pascarella_JSS_2018.pdf).
The features by Kamei are collected per commit this enables commit-level just-in-time defect prediction and enhances file-level just-in-time defect prediction with additional change context features.
The features by Pascarella are collected per file change.

### Static analysis warnings for Java and Python
In addition, Gierlappen supports static analysis warnings from [PMD](https://pmd.github.io/) for Java and [Pylint](https://pylint.org/) for Python.
Each static analysis warning is provided as a plain sum per file change and also in the for of warning density which is the sum of warnings divided by the logical lines of source code of the file.

### Maven build information
Gierlappen also supports collecting build information from Maven for Java.
It requires a local Maven installation as Maven is used to build an effective POM which includes all modules and parent POMs from Maven Central. The POM extraction allows fetching custom rules for PMD that are configured and enables the calculation of warning density for only the rules that are enabled via the build configuration, instead of all rules available today in the supported PMD.
However, if older commits are mined there may need to be some manual intervention because of missing dependencies.


## Installation

After cloning the repository, create a virtualenv environment and install the requirements.

```bash
python -m venv .
source bin/activate
pip install -r requirements.txt
```

### Install PMD

If PMD is needed, it needs to be extracted into the checks/pmd/ folder of Gierlappen.
```bash
wget https://github.com/pmd/pmd/releases/download/pmd_releases%2F6.31.0/pmd-bin-6.31.0.zip
unzip pmd-bin-6.31.0.zip -d ./checks/
mv checks/pmd-bin-6.31.0/* ./checks/pmd/
```

### Install Pylint

For Pylint it is sufficient if Pylint is installed inside the virtualenv of Gierlappen.
It is already included in the requirements.txt.


## Run tests

```bash
source bin/activate
python -m unittest
```

## Usage without SmartSHARK

Although Gierlappen was designed to work with [SmartSHARK](https://smartshark.github.io) it can be used without it. It then just does not have static source code metrics provided by SmartSHARK plugins.
There is also no way to include bug-reports other than the built-in keyword approach.
This limits the resolution of bug-fixing file changes to bug-inducing file changes as there is no issue creation date
to provide a date boundary for the blame.

Only collect just-in-time and fine-grained just-in-time features:
```bash
source bin/activate
python jit_mining.py --project PROJECT_NAME --path PATH_TO_REPOSITORY --language java
```

Additionally collect PMD static analysis warnings:
```bash
source bin/activate
python jit_mining.py --project PROJECT_NAME --path PATH_TO_REPOSITORY --language java --use-linter
```

Same for Python with Pylint:
```bash
source bin/activate
python jit_mining.py --project PROJECT_NAME --path PATH_TO_REPOSITORY --language python --use-linter
```


## Usage with SmartSHARK

To use Gierlappen with [SmartSHARK](https://smartshark.github.io) it requires an accessible MongoDB containing the SmartSHARK database.
This can be the current 2.0 [dump](https://smartshark.github.io/dbreleases/) as that contains the static source code metrics and PMD warnings already.
As it uses [Pydriller](https://github.com/ishepard/pydriller) to traverse the Git commit graph it also requires a local clone of the repository. To support this *smartshark_dump_repository.py* can extract the stored clone from the SmartSHARK Database.

Exctract clone from SmartSHARK:
```bash
source bin/activate
python smartshark_dump_repository --project PROJECT_NAME --path LOCAL_PATH --db-host SMARTSHARK_MONGODB_HOST --db-port SMARTSHARK_MONGODB_PORT --db-name SMARTSHARK_MONGODB_DATABASE --db-user SMARTSHARK_MONGODB_USER --db-pw SMARTSHARK_MONGODB_PASSWORD --db-auth SMARTSHARK_MONGODB_AUTHENTICATION_SOURCE

# example
# python smartshark_dump_repository.py --project ant-ivy --path /srv/repos/ --db-host 127.0.0.1 --db-port 27017 --db-name smartshark --db-user USER --db-pw PW --db-auth smartshark
```

If the repository is not existing locally it has to be extracted from the SmartSHARK database. Note that LOCAL_PATH is the base path for the extraction, e.g., /srv/repos/ it does not contain the project name.
A directory with the project name will be created in the directory containing the snapshot of the repository at the time of data collection.


Execute Gierlappen for SmartSHARK projects:
```bash
source bin/activate
python smartshark_mining.py --project PROJECT_NAME --path PATH_TO_REPOSITORY --label-name SMARTSHARK_BUG_LABEL --db-host SMARTSHARK_MONGODB_HOST --db-port SMARTSHARK_MONGODB_PORT --db-name SMARTSHARK_MONGODB_DATABASE --db-user SMARTSHARK_MONGODB_USER --db-pw SMARTSHARK_MONGODB_PASSWORD --db-auth SMARTSHARK_MONGODB_AUTHENTICATION_SOURCE

# example
# python smartshark_mining.py --project ant-ivy --path /srv/repos/ant-ivy/ --label-name JLMIV+R --db-host 127.0.0.1 --db-port 27017 --db-name smartshark --db-user USER --db-pw PW --db-auth smartshark
```

## Results

Gierlappen creates CSV files which contain the commit, file, date of commit as well as all enabled features. In addition the results contain a bug-matrix which can be used for time-sensitive evaluation of predictive models created with the data.

