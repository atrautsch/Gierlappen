"""Encapsulates pom.xml parsing to extract build information."""
import os
import logging
import subprocess
import shutil
import pickle

import networkx as nx
from lxml import etree

from const import DEFAULT_RULES_MAVEN, PMD_OLD_RULESETS

POM_NS = {'m' : 'http://maven.apache.org/POM/4.0.0'}
BUILD_FILES = ['/pom.xml', '/project.xml']


class PomPomError(Exception):
    """Encapsulate and differntiate between possible PomPom errors.

    We need to know what error was due to missing parent, parse errors etc.
    """
    def __init__(self, output):
        self.output = output
        self.type = 'unknown'
        self.line = ''

        error_types = {
            'unknown': None,
            'version_missing': 'dependencies.dependency.version',
            'plugin_missing': 'Plugin not found in any plugin repository',
            'unique': 'duplicate declaration of version',
            'parse': 'Non-parseable POM',
            'parent': 'Non-resolvable parent POM for',
            'malformed': 'Malformed POM',
            'buildext': 'Unresolvable build extension',
            'child': 'Child module',
            'unknown_packaging': 'Unknown packaging',
        }

        for k, v in error_types.items():
            if v and v in output:
                self.type = k

        for line in output.split('\n'):
            if error_types[self.type] and error_types[self.type] in line:
                self.line = line

        super().__init__('mvn help:effective-pom error')


class PomPom():
    """Maven buildfile parser for repository mining."""

    def __init__(self, project_root):
        self.poms = {}
        self._cache = {}
        self._build_information = {}
        self._log = logging.getLogger('jit.build')
        self._project_root = project_root
        if self._project_root.endswith('/'):
            self._project_root = self._project_root[:-1]

    def load_cache(self, cache_file):
        with open(cache_file, 'rb') as f:
            self._cache = pickle.load(f)

    def save_cache(self, cache_file):
        with open(cache_file, 'wb') as f:
            pickle.dump(self._cache, f)

    def get_file_metrics(self, file_path):
        tmp = {'use_maven': False,
               'use_pmd': False,
               'use_checkstyle': False,
               'use_findbugs': False,
               'use_custom_rules': False,
               'custom_rules': set()}

        if self._build_information:
            tmp['use_maven'] = True

        for build_source, values in self._build_information.items():
            if file_path.startswith(build_source):
                tmp['use_pmd'] = values['use_pmd']
                tmp['use_findbugs'] = values['use_findbugs']
                tmp['use_checkstyle'] = values['use_checkstyle']
                tmp['use_custom_rules'] = len(values['custom_rule_files']) > 0
                tmp['custom_rules'] = values['rules']
        return tmp

    def add_commit(self, commit):
        """Connector method, called from tracking."""
        revision_hash = commit.hash
        extract = False
        for mod in commit.modifications:
            if not mod.new_path:
                continue
            path = '/' + mod.new_path
            if path.endswith(tuple(BUILD_FILES)):
                extract = True

        # only change _build_information if a build has really changed
        if not extract:
            return

        try:
            self._log.info('[%s] detected build change, extracting new build status', revision_hash)
            self._build_information = self.get_build(revision_hash)
            self._log.debug('extract build information from commit %s', revision_hash)
        except PomPomError as e:
            if e.type == 'child':
                self._log.warning('missing child module in pom tree, keeping the old state')
            elif e.type in ['malformed', 'parse', 'unique', 'version_missing', 'unknown_packaging']:
                self._log.warning('malformed pom.xml (%s), skipping', e.type)
            elif e.type == 'plugin_missing':
                self._log.warning('plugin missing in pom, skipping')
            elif e.type == 'parent':
                self._log.warning('parent pom error %s', e.output)
            else:
                self._log.exception(e)
                raise e
        except etree.XMLSyntaxError as e:
            self._log.warning('XML Syntax error "%s", keeping the old build state', e)

    def get_build(self, revision_hash):
        if revision_hash in self._cache.keys():
            return self._cache[revision_hash]
        self._cache[revision_hash] = {}

        self.poms = {}
        poms = {}
        double_poms = set()
        for pom in self.get_main_poms():
            out, replacements = self.create_effective_pom(self._project_root + pom)
            poms[pom] = {'out': out, 'replacements': replacements}

        for poma, v in poms.items():
            all_idents = set()
            pom_idents = self.parse_ident(v['out'])

            all_idents.update(pom_idents)
            for pomb, v2 in poms.items():
                if poma == pomb:
                    continue

                pom_idents = self.parse_ident(v2['out'])

                if all_idents.intersection(pom_idents):
                    double_poms.add(pomb)
                all_idents.update(pom_idents)

        # chose the shortest pom if we have duplicates
        if double_poms:
            shortest = min(double_poms, key=len)
            self._log.warning('keeping %s pom in overlapping', shortest)
            for dpom in double_poms:
                if dpom != shortest:
                    del poms[dpom]
                    self._log.warning('overlapping project idents for pom %s, removing', dpom)

        # final pom list
        for pom, v in poms.items():
            if v['replacements']:
                self._log.info('[%s] replacements: %s', pom, v['replacements'])
            for pom_ident, values in self.parse_effective_pom(v['out']).items():
                if values['source_directory'] in self._cache[revision_hash].keys():
                    self._log.warning('overwriting source dir %s with values %s with %s', values['source_directory'], self._cache[revision_hash][values['source_directory']], values)
                self._cache[revision_hash][values['source_directory']] = values
        return self._cache[revision_hash]

    def _get_modules(self, xml):
        module_names = []
        modules = xml.xpath('m:modules/m:module', namespaces=POM_NS)
        for module in modules:
            module_names.append(module.text)
        return module_names

    def _get_parent_artifact(self, xml):
        artifact_id = ''
        parent = xml.xpath('m:parent', namespaces=POM_NS)
        if not parent:
            return artifact_id
        artifact = parent[0].find('m:artifactId', namespaces=POM_NS)
        if artifact is not None:
            artifact_id = artifact.text
        return artifact_id

    def _parse(self, filepath):
        data = ''
        with open(filepath, 'rb') as f:
            for line in f.readlines():
                if line.decode('utf-8', 'ignore'):
                    data += line.decode('utf-8', 'ignore')

        return etree.fromstring(data.encode('utf-8'))

    def _replace_parent_in_pom(self, pomfile):
        ns = {'m': 'http://maven.apache.org/POM/4.0.0'}

        # I really whish I would not have to do this
        with open(pomfile, 'rb') as f:
            data = f.read().decode('utf-8', 'ignore')

        doc = etree.fromstring(data.encode('utf-8'))

        gnode = doc.find('m:parent/m:groupId', namespaces=ns)
        anode = doc.find('m:parent/m:artifactId', namespaces=ns)
        vnode = doc.find('m:parent/m:version', namespaces=ns)
        rnode = doc.find('m:parent/m:relativePath', namespaces=ns)

        group_id = ''
        artifact_id = ''
        version = ''
        if gnode is not None:
            group_id = gnode.text
        if anode is not None:
            artifact_id = anode.text
        if vnode is not None:
            version = vnode.text

        # replacement rules here
        replacement = []
        if group_id == 'org.apache.commons' and artifact_id == 'commons':
            artifact_id = 'commons-parent'
            replacement.append({'old': 'commons', 'new': artifact_id})
            anode.text = artifact_id

        if group_id == 'org.apache.commons' and artifact_id == 'commons-sandbox':
            artifact_id = 'commons-sandbox-parent'
            replacement.append({'old': 'commons-sandbox', 'new': artifact_id})
            anode.text = artifact_id

        if group_id == 'org.apache.commons' and artifact_id == 'commons-sandbox-parent' and version == '1.0-SNAPSHOT':
            new_version = '1'
            replacement.append({'old': version, 'new': new_version})
            vnode.text = new_version
            version = new_version

        if group_id == 'org.apache.opennlp' and artifact_id == 'opennlp-reactor':
            artifact_id = 'opennlp'
            replacement.append({'old': 'opennlp-reactor', 'new': artifact_id})
            anode.text = artifact_id

        # not working
        # if pomfile.endswith('invertedindex/pom.xml') and group_id == 'org.apache.kylin' and artifact_id == 'kylin' and version == '0.7.1-SNAPSHOT':
        #     new_version = version.replace('-SNAPSHOT', '-incubating-SNAPSHOT')
        #     replacement.append({'old': version, 'new': new_version})
        #     vnode.text = new_version
        #     version = new_version

        # snapshot is probably not available anymore but only if it does not refer to a local pom via relativePath
        if '-SNAPSHOT' in version and rnode is None:
            new_version = version.replace('-SNAPSHOT', '')
            replacement.append({'old': version, 'new': new_version})
            vnode.text = new_version
            version = new_version

        # mahout has parent pointing to 0.1 but only 0.2 is in maven repository
        # Failure to find org.apache.mahout:mahout:pom:0.2-SNAPSHOT
        # if group_id == 'org.apache.wss4j' and artifact_id == 'wss4j-parent'

        # streams
        if group_id == 'org.apache.streams' and artifact_id == 'streams-master' and version in ['0.1-SNAPSHOT', '0.1']:
            new_version = '0.1-incubating'
            replacement.append({'old': version, 'new': new_version})
            vnode.text = new_version
            version = new_version

        if group_id == 'org.apache.streams' and artifact_id == 'streams-master' and version in ['0.2-SNAPSHOT', '0.2']:
            new_version = '0.2-incubating'
            replacement.append({'old': version, 'new': new_version})
            vnode.text = new_version
            version = new_version

        if group_id == 'org.apache.streams' and artifact_id == 'streams-master' and version in ['0.3-SNAPSHOT', '0.3']:
            new_version = '0.3-incubating'
            replacement.append({'old': version, 'new': new_version})
            vnode.text = new_version
            version = new_version

        if group_id == 'org.apache.streams.osgi-components' and artifact_id == 'streams-osgi-components' and version in ['0.1-SNAPSHOT', '0.1']:
            new_version = '0.1-incubating'
            replacement.append({'old': version, 'new': new_version})
            vnode.text = new_version
            version = new_version

        # 1.0 is invalid only 1 is valid in this case
        if group_id == 'org.apache.commons' and artifact_id == 'commons-parent' and '.' in version:
            new_version = version.split('.')[0]
            replacement.append({'old': version, 'new': new_version})
            vnode.text = new_version

        if replacement:
            with open(pomfile, 'wb') as f:
                f.write(etree.tostring(doc))
        return replacement

    def create_effective_pom(self, pom_file):
        """Create effective POM.
        This uses Maven which automatically includes parent POMS from maven central.
        """
        basedir = os.path.dirname(pom_file)

        # call help:effective-pom to generate the effective pom the project uses
        r = subprocess.run(['mvn', 'help:effective-pom', '-B', '-U'], cwd=basedir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        replacements = []
        out = r.stdout

        # if this did not work we try to replace stuff
        if r.returncode != 0:

            # check if it is a syntax error
            e = PomPomError(out.decode('utf-8'))
            if e.type == 'syntax':
                raise e

            self._log.warning('effective pom %s in "%s" exited with status %s and error %s and stdout %s', pom_file, basedir, r.returncode, r.stderr, r.stdout)
            # but only in the main pom.xml
            replacements = self._replace_parent_in_pom(pom_file)
            r2 = subprocess.run(['mvn', 'help:effective-pom', '-B', '-U'], cwd=basedir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out = r2.stdout
            # if we still error we bail
            if r2.returncode != 0:
                e = PomPomError(out.decode('utf-8'))
                self._log.warning('effective pom %s in "%s" exited with status %s and error %s and stdout %s, replacements: %s', pom_file, basedir, r2.returncode, r2.stderr, r2.stdout, replacements)
                raise PomPomError(r2.stdout.decode('utf-8'))

        return out, replacements

    def get_main_poms(self):
        """Returns the main pom.xml

        Get all pom.xml in projec dir and build a tree, return only roots (there can be multiple roots).
        """
        main_poms = set()

        if not os.path.isfile(os.path.join(self._project_root, 'pom.xml')) and os.path.isfile(os.path.join(self._project_root, 'project.xml')):
            self._log.warning('rename project.xml -> pom.xml')
            shutil.copyfile(os.path.join(self._project_root, 'project.xml'), os.path.join(self._project_root, 'pom.xml'))

        # if we are here we need to look for the main pom.xml
        # it should be the file to which others link the most as parent
        g = nx.DiGraph()
        for root, dirs, files in os.walk(self._project_root):
            for filepath in files:
                absolute_filepath = os.path.join(root, filepath)
                relative_filepath = absolute_filepath.replace(self._project_root, '')

                if relative_filepath.endswith('/pom.xml'):
                    folder = '.'.join(os.path.dirname(relative_filepath[1:]).split('/'))
                    g.add_node(absolute_filepath)

        # now establish the links between parents and childs for the builld tree
        for node in g:
            xml = self._parse(node)
            # look for parent references and potential modules to identify main pom.xml files
            artifact = self._get_parent_artifact(xml)
            modules = self._get_modules(xml)

            relative_filepath = node.replace(self._project_root, '')
            folder = '.'.join(os.path.dirname(relative_filepath[1:]).split('/'))

            # do we have a local parent?
            parent_path = node.replace(folder, artifact)
            if artifact and os.path.exists(parent_path):
                g.add_edge(parent_path, node)

            # modules should always be local
            for child in modules:
                child_path = node.replace('/pom.xml', '/{}/pom.xml'.format(child.replace('.', '/')))
                if os.path.exists(child_path):
                    g.add_edge(node, child_path)
                    # self._log.debug('found child %s for %s', child_path, node)
                else:
                    self._log.error('missing child %s from %s', child_path, node)

        for node, num_parents in g.in_degree():
            if num_parents > 0:
                continue
            if node.endswith(('/example/', '/examples/', '/parquet-hive/', '/experimental/', '/engine/', '/giraph-formats-contrib/pom.xml', '/giraph-formats/pom.xml', '/giraph-hcatalog/pom.xml', '/giraph-hbase/pom.xml')):
                continue
            main_poms.add(node.replace(self._project_root, ''))

        self._log.debug('final root poms %s', main_poms)
        return main_poms

    def _relative_path(self, path):
        # self._log.debug('call to relpath with %s', path)
        subtract = self._project_root
        if not self._project_root.endswith('/'):
            subtract += '/'
        return path.replace(subtract, '')

    def find_file(self, needle):
        self._log.debug('find file %s', needle)
        return needle
#    def _read_pmd_rules(self, path):
#        self._log.debug('read pmd rules with %s', path)

    def _read_pmd_rules(self, absolute_filepath):
        """The remote file could also be a ruleset."""

        groups_expanded = False

        # if self.project_name in CUSTOM_PATHS:
        #     if rel_path_file in CUSTOM_PATHS[self.project_name].keys():
        #         file1 = self.basedir + rel_path_file
        #         file2 = self.basedir + CUSTOM_PATHS[self.project_name][rel_path_file]['new_file']

        #         print('replacing')
        #         if not os.path.isfile(file1) and os.path.isfile(file2):
        #             print('replacing {} with {}'.format(rel_path_file, CUSTOM_PATHS[self.project_name][rel_path_file]['new_file']))
        #             rel_path_file = CUSTOM_PATHS[self.project_name][rel_path_file]['new_file']

#                if self.revision_hash in CUSTOM_PATHS[self.project_name][rel_path_file]['revisions']:

        rules = set()

        # group expansion for files in the form ruleset>/rulesets/braces.xml</ruleset>
        # absolute_filepath = self._project_root + '/' + absolute_filepath
        if not os.path.isfile(absolute_filepath):
            self._log.warning('no such custom rule file %s, trying group expansion', absolute_filepath)
            category = absolute_filepath.split('/')[-1].split('.')[0].lower()
            if category in PMD_OLD_RULESETS.keys():
                groups_expanded = True
                rules = set()
                # 1. get rules from category
                pmd_names = PMD_OLD_RULESETS[category]

                for pmd_name in pmd_names.split(','):
                    k = pmd_name.strip()
                    rules.add(k)
                    #if k in PMD_NAME_TO_SM.keys():
                    #    rules.add(PMD_NAME_TO_SM[k])
            else:
                self._log.error('custom rule file %s, could not find category %s', absolute_filepath, category)
                # raise Exception('error in group expansion')  this happens when checkstyle.xml files are used for pmd (e.g., in commons-math, commons-validator)
                #if self.project_name in CUSTOM_RULE_PROBLEMS.keys() and rel_path_file in CUSTOM_RULE_PROBLEMS[self.project_name]:
                #    groups_expanded = True
                #    return [], groups_expanded

            return rules, groups_expanded

        doc = etree.parse(absolute_filepath)
        root = doc.getroot()

        ns = {}
        if root.nsmap:
            ns = {'m': root.nsmap[None]}  # root.nsmap returns the dict with default namespace as None

        # this is only here because of the namespaces
        def query_ns(obj, path, ns):
            if ns:
                return obj.xpath(path, namespaces=ns)
            return obj.xpath(path.replace('m:', ''))

        for rule in query_ns(doc, '//m:rule', ns):

            # some rules do not have a ref because they are fully custom
            # we can not have them in our data because they will not be available in the Sourcemeter PMD rulesets
            # therefore we skip them
            if 'ref' not in rule.attrib.keys():
                continue

            # this handles single rules, e.g., <rule ref="rulesets/java/comments.xml/CommentSize">
            if not rule.attrib['ref'].endswith('.xml'):
                k = rule.attrib['ref'].split('/')[-1]
                rules.add(k)
                continue
                #if k in PMD_NAME_TO_SM.keys():
                #    rules.add(PMD_NAME_TO_SM[k])
                #continue

            # if this fails that is critical, that means we have hit an unknown category
            category = rule.attrib['ref'].split('/')[-1].split('.')[0]

            # rule expansion from category
            try:
                pmd_names = PMD_OLD_RULESETS[category]

            except KeyError as e:
                self._log.error('ruleset %s not found in [%s]', category, ','.join(PMD_OLD_RULESETS.keys()))
                raise

            for pmd_name in pmd_names.split(','):
                k = pmd_name.strip()
                rules.add(k)
                #if k in PMD_NAME_TO_SM.keys():
                #    rules.add(PMD_NAME_TO_SM[k])

            for exclude in query_ns(rule, 'm:exclude', ns):
                k = exclude.attrib['name']
                if k in rules:
                    rules.remove(k)
                #if k in PMD_NAME_TO_SM.keys() and PMD_NAME_TO_SM[k] in rules:
                #    rules.remove(PMD_NAME_TO_SM[k])

        if not rules:
            groups_expanded = True
            self._log.warning('empty pmd rules for file %s', absolute_filepath)

        return rules, groups_expanded

    def parse_ident(self, file):
        ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
        data = ''
        in_xml = False
        multi_project = False
        for line in file.decode('utf-8', 'ignore').split('\n'):
            if line.strip().startswith('<?xml'):
                in_xml = True
            if line.strip().startswith('<projects>'):
                multi_project = True
            if in_xml:
                data += line
            # closing tag is dependent on multi project pom
            if not multi_project and line.strip().startswith('</project>'):
                in_xml = False
            if multi_project and line.strip().startswith('</projects>'):
                in_xml = False

        doc = etree.fromstring(data.encode('utf-8'))
        idents = set()
        for project in doc.xpath('//m:project', namespaces=ns):
            gid = project.find('m:groupId', namespaces=ns)
            aid = project.find('m:artifactId', namespaces=ns)
            ver = project.find('m:version', namespaces=ns)

            if gid is not None:
                ident = gid.text
            else:
                ident = 'unknown'

            if aid is not None:
                ident += ':' + aid.text
            else:
                ident += ':unknown'

            if ver is not None:
                ident += '-' + ver.text
            else:
                ident += '-unknown'

            idents.add(ident)
        return idents

    def parse_effective_pom(self, file):
        """
        Read Pom from passed file (effective pom).

        The file can consist of multiple POMs via a top level <projects> in the xml string, those are
        translated to idents via their groupId and artifactId which then hold a separate state for each
        pom.
        """
        ns = {'m': 'http://maven.apache.org/POM/4.0.0'}

        # I really whish I would not have to do this
        # a) we are discarding every line not starting included in the xml because help:effective-pom outputs more than the xml to stdout
        # b) we are ignoring non utf-8 chars because some projects have them in utf-8 encoded xml files
        data = ''
        in_xml = False
        multi_project = False
        for line in file.decode('utf-8', 'ignore').split('\n'):
            if line.strip().startswith('<?xml'):
                in_xml = True
            if line.strip().startswith('<projects>'):
                multi_project = True
            if in_xml:
                data += line
            # closing tag is dependent on multi project pom
            if not multi_project and line.strip().startswith('</project>'):
                in_xml = False
            if multi_project and line.strip().startswith('</projects>'):
                in_xml = False

        # with open(file, 'rb') as f:
        #     for line in f.readlines():
        #         if line.decode('utf-8', 'ignore').strip().startswith('<'):
        #             data += line

        doc = etree.fromstring(data.encode('utf-8'))

        for project in doc.xpath('//m:project', namespaces=ns):
            gid = project.find('m:groupId', namespaces=ns)
            aid = project.find('m:artifactId', namespaces=ns)
            ver = project.find('m:version', namespaces=ns)

            if gid is not None:
                ident = gid.text
            else:
                ident = 'unknown'

            if aid is not None:
                ident += ':' + aid.text
            else:
                ident += ':unknown'

            if ver is not None:
                ident += '-' + ver.text
            else:
                ident += '-unknown'

            if ident in self.poms.keys():
                raise Exception('duplicate project ident: {}'.format(ident))

            # set defaults for this project
            self.poms[ident] = {'use_pmd': False,
                                'use_checkstyle': False,
                                'use_findbugs': False,
                                'use_spotbugs': False,
                                'use_sonarcube': False,
                                'use_errorprone': False,
                                'custom_rule_files': set(),
                                'exclude_roots': set(),
                                'excludes': set(),
                                'includes': set(),
                                'include_tests': False,
                                'exclude_from_failure': set(),
                                'language': 'java',
                                'rules': set(),
                                'minimum_priority': 5,
                                'source_directory': None,
                                'test_source_directory': None,
                                'plugin_build': 0,
                                'plugin_reporting': 0,
                                }
            # we just want to know if it is there
            if len(project.xpath('//m:plugins/m:plugin[m:artifactId = "maven-checkstyle-plugin"]', namespaces=ns)) > 0:
                self.poms[ident]['use_checkstyle'] = True
            if len(project.xpath('//m:plugins/m:plugin[m:artifactId = "findbugs-maven-plugin"]', namespaces=ns)) > 0:
                self.poms[ident]['use_findbugs'] = True
            if len(project.xpath('//m:plugins/m:plugin[m:artifactId = "spotbugs-maven-plugin"]', namespaces=ns)) > 0:
                self.poms[ident]['use_spotbugs'] = True
            # taken from: https://github.com/apache/wss4j/blob/trunk/pom.xml#L248
            if len(project.xpath('//m:path[m:groupId = "com.google.errorprone"]', namespaces=ns)) > 0:
                self.poms[ident]['use_errorprone'] = True

            if len(project.xpath('//m:dependency[m:groupId = "com.google.errorprone"]', namespaces=ns)) > 0:
                self.poms[ident]['use_errorprone'] = True

            # detects sonar inclusion for maven-reporting
            # taken from: https://github.com/apache/helix/blob/master/pom.xml#L814
            if len(project.xpath('//m:plugins/m:plugin[m:groupId = "org.codehaus.sonar-plugins"]', namespaces=ns)) > 0:
                self.poms[ident]['use_sonarcube'] = True

            for sd in project.xpath('m:build/m:sourceDirectory', namespaces=ns):
                self.poms[ident]['source_directory'] = self._relative_path(sd.text)

            for td in project.xpath('m:build/m:testSourceDirectory', namespaces=ns):
                self.poms[ident]['test_source_directory'] = self._relative_path(td.text)

            # early return for not having the plugin
            if len(project.xpath('//m:plugins/m:plugin[m:artifactId = "maven-pmd-plugin"]', namespaces=ns)) == 0:
                continue

            # if we find maven plugin we use pmd and set the default maven plugin rules
            self.poms[ident]['use_pmd'] = True
            self.poms[ident]['rules'] = set(DEFAULT_RULES_MAVEN)

            # how often does the plugin appear in build and reporting sections
            self.poms[ident]['plugin_build'] = len(project.xpath('m:build/m:plugins/m:plugin[m:artifactId = "maven-pmd-plugin"]', namespaces=ns))
            self.poms[ident]['plugin_reporting'] = len(project.xpath('m:reporting/m:plugins/m:plugin[m:artifactId = "maven-pmd-plugin"]', namespaces=ns))

            for plugin in project.xpath('m:reporting/m:plugins/m:plugin[m:artifactId = "maven-pmd-plugin"]', namespaces=ns) + project.xpath('m:build/m:plugins/m:plugin[m:artifactId = "maven-pmd-plugin"]', namespaces=ns) + project.xpath('m:reporting/m:pluginManagement/m:plugins/m:plugin[m:artifactId = "maven-pmd-plugin"]', namespaces=ns) + project.xpath('m:build/m:pluginManagement/m:plugins/m:plugin[m:artifactId = "maven-pmd-plugin"]', namespaces=ns):
                mp = plugin.find('m:configuration/m:minimumPriority', namespaces=ns)
                lang = plugin.find('m:configuration/m:language', namespaces=ns)
                sr = plugin.find('m:configuration/m:compileSourceRoots/m:compileSourceRoot', namespaces=ns)
                tr = plugin.find('m:configuration/m:testSourceRoots/m:testSourceRoot', namespaces=ns)
                inclt = plugin.find('m:configuration/m:includeTests', namespaces=ns)
                version = plugin.find('m:version', namespaces=ns)

                if mp is not None:
                    self.poms[ident]['minimum_priority'] = mp.text
                if lang is not None:
                    self.poms[ident]['language'] = lang.text.lower()
                if sr is not None:
                    # safety exception for conflicting source_directories if the plugin is defined in reporting and build
                    if self.poms[ident]['source_directory'] and self.poms[ident]['source_directory'] != sr.text:
                        raise Exception('duplicate source directory {} this happens if the plugin defines two source directories in build or reporting'.format(self._project_root))
                    self.poms[ident]['source_directory'] = sr.text
                if tr is not None:
                    self.poms[ident]['test_source_directory'] = tr.text
                if inclt is not None and inclt.text.lower() == 'true':
                    self.poms[ident]['include_tests'] = True
                if version is not None:
                    self.poms[ident]['version'] = version.text

                # this is a properties file not rule defs: https://maven.apache.org/plugins/maven-pmd-plugin/examples/violation-exclusions.html
                # also probably not in reporting but build
                for efr in plugin.xpath('m:configuration/m:excludeFromFailureFile', namespaces=ns):
                    self.poms[ident]['exclude_from_failure'].add(efr.text)

                for rs in plugin.xpath('m:configuration/m:rulesets/m:ruleset', namespaces=ns):
                    self.poms[ident]['custom_rule_files'].add(rs.text)

                for exclr in plugin.xpath('m:configuration/m:excludeRoots/m:excludeRoot', namespaces=ns):
                    self.poms[ident]['exclude_roots'].add(self._relative_path(exclr.text))

                for exclf in plugin.xpath('m:configuration/m:excludes/m:exclude', namespaces=ns):
                    for exfile in [d.strip() for d in exclf.text.split(',')]:
                        if exfile:
                            self.poms[ident]['excludes'].add(exfile)

                for inclf in plugin.xpath('m:configuration/m:includes/m:include', namespaces=ns):
                    self.poms[ident]['includes'].add(inclf.text)

                # remove default maven rules in case of custom defined rules
                if self.poms[ident]['custom_rule_files']:
                    self.poms[ident]['rules'] = set()

                custom_files = set()
                for custom_ruleset in self.poms[ident]['custom_rule_files']:
                    crules, groups_expanded = self._read_pmd_rules(custom_ruleset)
                    if not groups_expanded:
                        custom_files.add(custom_ruleset)
                    self.poms[ident]['rules'].update(crules)
                self.poms[ident]['custom_rule_files'] = custom_files
        return self.poms
