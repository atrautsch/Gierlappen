#!/bin/bash

cd $1

git init
git config user.name "Test User"
git config user.email "test@test.local"


export GIT_COMMITTER_DATE="2018-01-01 03:01:01 +0200"
export GIT_AUTHOR_DATE="2018-01-01 03:01:01 +0200"

cat << EOF > ./Main.java
public class Main {
	public static void main(String[] args) {

	}
}
EOF

git add Main.java
git commit -m "(a) init, added Main.java"


export GIT_COMMITTER_DATE="2018-01-03 03:01:01 +0200"
export GIT_AUTHOR_DATE="2018-01-03 03:01:01 +0200"

cat << EOF > ./Main.java
public class Main {
	public static void main(String[] args) {
		System.out.println("Hallo");
	}
}
EOF

git add Main.java
git commit -m "(b) add output"


export GIT_COMMITTER_DATE="2018-01-02 03:01:01 +0200"
export GIT_AUTHOR_DATE="2018-01-02 03:01:01 +0200"

cat << EOF > ./Main.java
public class Main {
	public static void main(String[] args) {
		//System.out.println("Hallo");
	}
}
EOF

git add Main.java
git commit -m "(c) fix, remove unneeded output"

