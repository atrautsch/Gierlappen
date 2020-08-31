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

# second user adds a bug and adds a second file
git config user.name "Test User2"
git config user.email "test2@test2.local"
export GIT_COMMITTER_DATE="2018-01-03 03:01:01 +0200"
export GIT_AUTHOR_DATE="2018-01-03 03:01:01 +0200"

cat << EOF > ./Main.java
public class Main {
	public static void main(String[] args) {
		System.out.println("Hallo");
	}
}
EOF

cat << EOF > ./Test.java
public class Test {
	public static void main(String[] args) {
	}
}
EOF

git add Main.java
git add Test.java
git commit -m "(b) add output and Test.java"


export GIT_COMMITTER_DATE="2018-01-04 03:01:01 +0200"
export GIT_AUTHOR_DATE="2018-01-04 03:01:01 +0200"

mv Main.java Rubbish.java
git add Rubbish.java 
git commit -a -m "(c) move file"

# back to first user for a fix
git config user.name "Test User"
git config user.email "test@test.local"
export GIT_COMMITTER_DATE="2018-01-05 03:01:01 +0200"
export GIT_AUTHOR_DATE="2018-01-05 03:01:01 +0200"

cat << EOF > ./Rubbish.java
public class Main {
	public static void main(String[] args) {
	}
}
EOF

cat << EOF > ./Test.java
public class Test {
	public static void main(String[] args) {
		System.out.println("Test Output");
	}
}
EOF


git add Test.java
git add Rubbish.java 
git commit -m "(d) fix, remove unneeded output, add output to Test.java"
