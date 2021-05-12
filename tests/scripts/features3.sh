#!/bin/bash

cd $1

git init
git config user.name "Test User"
git config user.email "test@test.local"


export GIT_COMMITTER_DATE="2018-01-01 03:01:01 +0200"
export GIT_AUTHOR_DATE="2018-01-01 03:01:01 +0200"

mkdir package1
mkdir package2
cat << EOF > ./package1/Main.java
public class Main {
	public static void main(String[] args) {
































































































	}
}
EOF

git add package1/Main.java
git commit -m "(a) init, added Main.java"

# second user changes less than 5%
git config user.name "Test User2"
git config user.email "test2@test2.local"
export GIT_COMMITTER_DATE="2018-01-03 03:01:01 +0200"
export GIT_AUTHOR_DATE="2018-01-03 03:01:01 +0200"

cat << EOF > ./package1/Main.java
public class Main {
	public static void main(String[] args) {
		System.out.println("lots of empty lines");































































































	}
}
EOF

git add package1/Main.java
git commit -m "(b) add output and Test.java"

