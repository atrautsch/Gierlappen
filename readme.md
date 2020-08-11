# Gierlappen: fine-grained just-in-time defect prediction data mining

This is a research prototype for mining fine-grained just-in-time defect predicition data. It is designed to maximize available data by traversing all branches and keeping track of state for every file on every branch.
The memory consumption is currently prohibitive and it may run out of memory on large repositories with a large number of files.
This is a work in progress.


## Installation

After cloneing the repository, we create a pip environment and install the requirements.

```bash
python -m venv .
source bin/activate
pip install -r requirements.txt
```


## Usage without SmartSHARK

Although Gierlappen was designed to work with [SmartSHARK](https://smartshark.github.io) it can be used without it. It then just does not have static source code metrics provided by SmartSHARK plugins. There is also no way to include bug-reports other than the built-in keyword approach.

```bash
source bin/activate
python jit_mining.py --project PROJECT_NAME --path PATH_TO_REPOSITORY --file-check
```


## Usage with SmartSHARK

To use Gierlappen with SmartSHARK it requires an accessible MongoDB containing the SmartSHARK database.
As it uses pydriller to traverse the Git commit graph it also requires a checked out version of the repository.

```bash
source bin/activate
python smartshark_mining.py --project PROJECT_NAME --path PATH_TO_REPOSITORY --file-check --label-name SMARTSHARK_BUG_LABEL --db-host SMARTSHARK_MONGODB_HOST --db-port SMARTSHARK_MONGODB_PORT --db-name SMARTSHARK_MONGODB_DATABASE --db-user SMARTSHARK_MONGODB_USER --db-pw SMARTSHARK_MONGODB_PASSWORD --db-auth SMARTSHARK_MONGODB_AUTHENTICATION_SOURCE

# example
# python smartshark_mining.py --project ant-ivy --path /srv/repos/ant-ivy/ --file-check --label-name JLMIV+R --db-host 127.0.0.1 --db-port 27017 --db-name smartshark --db-user USER --db-pw PW --db-auth smartshark
```

If the repository is not existing locally it has to be extracted from the SmartSHARK database. Note that LOCAL_PATH is the base path for the extraction, e.g., /srv/repos/ it does not contain the project name.
A directory with the project name will be created in the directory containing the snapshot of the repository at the time of data collection.

```bash
source bin/activate
python smartshark_dump_repository.py --project PROJECT_NAME --path LOCAL_PATH --db-host SMARTSHARK_MONGODB_HOST --db-port SMARTSHARK_MONGODB_PORT --db-name SMARTSHARK_MONGODB_DATABASE --db-user SMARTSHARK_MONGODB_USER --db-pw SMARTSHARK_MONGODB_PASSWORD --db-auth SMARTSHARK_MONGODB_AUTHENTICATION_SOURCE

# example
# python smartshark_dump_repository.py --project ant-ivy --path /srv/repos/ --db-host 127.0.0.1 --db-port 27017 --db-name smartshark --db-user USER --db-pw PW --db-auth smartshark
```



## Results

Gierlappen creates CSV files which contain the commit, file, date of commit as well as fine-grained just-in-time features. In addition the results contain a bug-matrix which can be used for time-sensitive evaluation of predictive models created with the data.
