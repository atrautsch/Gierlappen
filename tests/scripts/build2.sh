#!/bin/bash

# creates pom.xml and two submodules only one contains pmd rules
cd $1
DIR=$2

mkdir -p package1/package2
mkdir package3
mkdir main

cat << EOF > ./package1/pom.xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/maven-v4_0_0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <artifactId>$DIR</artifactId>
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

cat << EOF > ./package3/pom.xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/maven-v4_0_0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <artifactId>$DIR</artifactId>
    <groupId>local.test.$DIR</groupId>
    <version>1.0</version>
  </parent>
  <groupId>local.test.$DIR</groupId>
  <artifactId>package3</artifactId>
  <packaging>jar</packaging>
  <version>1.0-SNAPSHOT</version>
  <name>package3</name>
  <properties>
    <pmd.version>3.8</pmd.version>
    <compiler.target>1.8</compiler.target>
  </properties>
EOF

cat << 'EOF' >> ./package3/pom.xml
<build>
    <defaultGoal>install</defaultGoal>
    <plugins>
      <plugin>
        <artifactId>maven-pmd-plugin</artifactId>
        <version>${pmd.version}</version>
        <configuration>
          <targetJdk>${compiler.target}</targetJdk>
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
        <version>${pmd.version}</version>
        <configuration>
          <targetJdk>${compiler.target}</targetJdk>
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

cat << EOF > ./pom.xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/maven-v4_0_0.xsd">
	<modelVersion>4.0.0</modelVersion>

	<groupId>local.test.$DIR</groupId>
	<artifactId>$DIR</artifactId>
	<packaging>pom</packaging>
	<version>1.0</version>
	<name>$DIR</name>

	<modules>
		<module>package3</module>
		<module>package1</module>
	</modules>

</project>
EOF

cat << EOF > ./package3/pmd-ruleset.xml
<?xml version="1.0"?>
<!--
   Licensed to the Apache Software Foundation (ASF) under one or more
   contributor license agreements.  See the NOTICE file distributed with
   this work for additional information regarding copyright ownership.
   The ASF licenses this file to You under the Apache License, Version 2.0
   (the "License"); you may not use this file except in compliance with
   the License.  You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
-->
<ruleset name="commons-math-customized"
    xmlns="http://pmd.sourceforge.net/ruleset/2.0.0"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://pmd.sourceforge.net/ruleset/2.0.0 http://pmd.sourceforge.net/ruleset_2_0_0.xsd">
  <description>
    This ruleset checks the code for discouraged programming constructs.
  </description>

  <rule ref="rulesets/java/basic.xml"/>

  <rule ref="rulesets/java/braces.xml"/>

  <rule ref="rulesets/java/comments.xml">
    <exclude name="CommentSize"/>
  </rule>
  <rule ref="rulesets/java/comments.xml/CommentSize">
    <properties>
      <property name="maxLines"      value="200"/>
      <property name="maxLineLength" value="256"/>
    </properties>
  </rule>

  <rule ref="rulesets/java/empty.xml"/>

  <rule ref="rulesets/java/finalizers.xml"/>

  <rule ref="rulesets/java/imports.xml"/>

  <rule ref="rulesets/java/typeresolution.xml">
    <!-- TODO: we should reactivate this rule -->
    <exclude name="CloneMethodMustImplementCloneable"/>
  </rule>

  <!-- TODO: we should reactivate this ruleset -->
  <!-- <rule ref="rulesets/java/clone.xml"/> -->

  <rule ref="rulesets/java/unnecessary.xml">

    <!-- In many places in Apache Commons Math, there are complex boolean expressions.
         We do use extra parentheses there as most people do not recall operator precedence,
         this means even if the parentheses are useless for the compiler, we don't consider
         them useless for the developer. This is the reason why we disable this rule. -->
    <exclude name="UselessParentheses"/>

    <!-- At several places in the optimization package, we set up public "optimize" methods
         that simply call their base class optimize method. This is intentional and allows
         to update the javadoc and make sure the additional parameters implemented at the
         lower class level are properly documented. These new parameters are really taken
         into accound despite we merely call super.optimize because the top level optimze
         methods call a protected parseOptimizationData method implemented in the specialized
         class. This is the reason why we disable this rule. -->
    <exclude name="UselessOverridingMethod"/>

  </rule>

</ruleset>
EOF

