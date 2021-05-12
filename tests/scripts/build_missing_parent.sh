#!/bin/bash

cd $1

cat << EOF > ./pom.xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/maven-v4_0_0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>local.test</groupId>
    <artifactId>main</artifactId>
    <packaging>pom</packaging>
    <version>1.0</version>
    <name>main</name>
    <parent>
        <groupId>not.existing</groupId>
        <artifactId>missing-parent</artifactId>
        <version>1</version>
    </parent>
</project>
EOF
