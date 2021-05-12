#!/bin/bash

cd $1
DIR=$2


cat << EOF > ./pom.xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/maven-v4_0_0.xsd">
	<modelVersion>4.0.0</modelVersion>

	<groupId>local.test.$DIR</groupId>
	<artifactId>main</artifactId>
	<packaging>pom</packaging>
	<version>1.0</version>
	<name>main</name>
  <build>
EOF

cat << 'EOF' >> ./pom.xml
  <defaultGoal>install</defaultGoal>
    <plugins>
      <plugin>
        <artifactId>maven-pmd-plugin</artifactId>
        <version>3.8</version>
        <configuration>
          <targetJdk>1.8</targetJdk>
          <skipEmptyReport>false</skipEmptyReport>
          <rulesets>
            <ruleset>${basedir}/pmd-ruleset.xml</ruleset>
          </rulesets>
        </configuration>
      </plugin>
    </plugins>
  </build>
  <reporting>
    <plugins>
      <plugin>
        <artifactId>maven-pmd-plugin</artifactId>
        <version>3.8</version>
        <configuration>
          <targetJdk>1.8</targetJdk>
          <skipEmptyReport>false</skipEmptyReport>
          <rulesets>
            <ruleset>${basedir}/pmd-ruleset.xml</ruleset>
          </rulesets>
        </configuration>
        <reportSets>
          <reportSet>
            <reports>
              <report>pmd</report>
            </reports>
          </reportSet>
        </reportSets>
      </plugin>
     </plugins>
  </reporting>

</project>

EOF


cat << EOF > ./pmd-ruleset.xml
<?xml version="1.0"?>
<ruleset name="commons-math-customized"
    xmlns="http://pmd.sourceforge.net/ruleset/2.0.0"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://pmd.sourceforge.net/ruleset/2.0.0 http://pmd.sourceforge.net/ruleset_2_0_0.xsd">
  <description>
  </description>

  <rule ref="rulesets/java/basic.xml"/>

  <rule ref="rulesets/java/imports.xml">
    <exclude name="DuplicateImports"/>
  </rule>

</ruleset>
EOF

