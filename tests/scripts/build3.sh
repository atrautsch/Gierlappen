#!/bin/bash

cd $1
DIR=$2

mkdir package3
mkdir -p main/package1

cat << EOF > ./main/package1/pom.xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/maven-v4_0_0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <artifactId>main</artifactId>
    <groupId>local.test.$DIR</groupId>
    <version>1.0</version>
  </parent>
  <groupId>local.test.$DIR</groupId>
  <artifactId>package1</artifactId>
  <packaging>jar</packaging>
  <version>1.0-SNAPSHOT</version>
  <name>package1</name>
</project>
EOF

cat << EOF > ./main/pom.xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/maven-v4_0_0.xsd">
	<modelVersion>4.0.0</modelVersion>

	<groupId>local.test.$DIR</groupId>
	<artifactId>main</artifactId>
	<packaging>pom</packaging>
	<version>1.0</version>
	<name>main</name>

	<modules>
		<module>package1</module>
	</modules>

</project>

EOF



