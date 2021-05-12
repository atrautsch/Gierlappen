#!/bin/bash

cd $1

git init
git config user.name "Test User"
git config user.email "test@test.local"


export GIT_COMMITTER_DATE="2018-01-01 03:01:01 +0200"
export GIT_AUTHOR_DATE="2018-01-01 03:01:01 +0200"

mkdir package1
mkdir package2
cat << EOF > ./package1/main.py
import os

def main():
    print('hello world')

EOF

cat << EOF > ./package2/main.py
def main():
    print('hello world')
EOF


git add package1/main.py
git add package2/main.py
git commit -m "(a) init, added main.py for both packages"

# second user adds a bug and adds a second file
git config user.name "Test User2"
git config user.email "test2@test2.local"
export GIT_COMMITTER_DATE="2018-01-03 03:01:01 +0200"
export GIT_AUTHOR_DATE="2018-01-03 03:01:01 +0200"

mkdir package3
cat << EOF > ./package1/main.py
import os

def main():
    print('hello world')
    print('hallo world 2')

EOF

cat << EOF > ./package3/test.py
def test():
    print('just a test')

EOF

git add package1/main.py
git add package3/test.py
git commit -m "(b) add output and test.py"


export GIT_COMMITTER_DATE="2019-02-04 03:01:01 +0200"
export GIT_AUTHOR_DATE="2019-02-04 03:01:01 +0200"

# back to first user
git config user.name "Test User"
git config user.email "test@test.local"

cat << EOF > ./package1/main.py
import os

def main():
    pass

EOF

#cat << EOF > ./package2/Main.java
#public class Main {
	#public static void main(String[] args) {
		#//System.out.println("hallo");
	#}
#}
#EOF


#cat << EOF > ./Test.javallllllllll
#public class Test {
	#public static void main(String[] args) {
		#System.out.println("Test Output");
	#}
#}
#EOF


#git add Test.java
git add package1/main.py
#git add package2/Main.java
git commit -m "(d) fix, remove unneeded output, add output to test.py"


