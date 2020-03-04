# coding=utf-8

#
# Copyright Zucker
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os
import sys
import subprocess
from shutil import copyfile
import shutil
import re
import zipfile
import copy
from pathlib import Path


class CloneProject:
    target_project_name = ""

    def clone(self, current_path, output_path, target_project_name, output_project_name):
        self.target_project_name = target_project_name
        # 如果output目录不存在，则创建文件夹
        if not os.path.exists(output_path):
            os.mkdir(output_path)
        self.__copy_dir(current_path, output_path, output_project_name, 0)

    # 拷贝文件夹
    def __copy_dir(self, source_dir, target_dir, target, index):
        # 源文件夹
        dir = os.path.join(source_dir, target)
        if index == 0:
            dir = os.path.join(source_dir, self.target_project_name)
        else:
            dir = os.path.join(source_dir, target)
        # 源文件夹下的文件列表
        files = os.listdir(dir)
        # 目标文件夹
        target_dir = os.path.join(target_dir, target)
        if not os.path.exists(target_dir):
            os.mkdir(target_dir)
        if index == 0:
            self.fileSize = 0
            for dirpath, dirnames, filenames in os.walk(dir):
                for file in filenames:
                    self.fileSize = self.fileSize + 1
            self.count = 0
        for f in files:
            sourcefile = os.path.join(dir, f)
            targetfile = os.path.join(target_dir, f)
            if os.path.isdir(sourcefile):
                index += 1
                self.__copy_dir(dir, target_dir, f, index)
            if os.path.isfile(sourcefile) and not os.path.exists(targetfile):
                copyfile(sourcefile, targetfile)
                self.count += 1
                print("Cloning: {0}%".format(round((self.count + 1) * 100 / self.fileSize)), end="\r")


class TreeNode:
    children = set()
    parents = set()
    parent = None
    value = ""

    def __init__(self, value):
        self.value = value
        self.children = set()
        self.parents = set()
        self.parent = None

    def add_child(self, node):
        self.children.add(node)

    def add_parent(self, node):
        self.parent = node
        self.parents.add(node)

    def is_root(self):
        return len(self.parents) == 0 or self.parent is None

    def get_level(self):
        if self.is_root():
            return 0
        return self.parent.get_level() + 1


class Dependency:
    # gradle命令，获取release下依赖树，写入文件
    commend = "./gradlew -q dependencies :%s:dependencies  --configuration releaseRuntimeClasspath>"
    # 去重set
    __node_set = set()
    # root节点
    rootNode = None
    # 记录当前的节点
    stack = []
    # 所有依赖节点
    allNode = []
    # 移除support包和Android原生依赖包
    exportArr = ["com.android.support", "android.arch.lifecycle", "com.google.android",
                 "com.squareup.leakcanary:leakcanary-android", "android.arch.core",
                 "org.jetbrains.kotlin:kotlin-stdlib-common", "org.jetbrains:annotations",
                 "androidx.", "project :"]

    def __init__(self, output_project_path, app_dir):
        self.file_name = "dependency_" + app_dir + ".txt"
        self.projectPath = output_project_path
        self.appDir = app_dir

    def get_top_level_aars(self):
        self.rootNode = TreeNode(self.appDir)
        self.stack.append(self.rootNode)
        self.allNode.append(self.rootNode)
        # 执行gradle命令
        self.commend = (self.commend % self.appDir) + os.path.join(self.projectPath, self.file_name)
        # cd到工程目录下，才能正常的读取gradle命令
        self.commend = ("cd %s\nchmod +x gradlew\n" % self.projectPath) + self.commend
        subprocess.check_call(self.commend, shell=True)
        self.__check_dependency_file()

        nodes = []
        for n in self.allNode:
            nodeName = n.value
            if len(n.parents) >= 1 and not self.__check_aar_in_export(nodeName):
                for p in n.parents:
                    if p == self.rootNode:
                        nodes.append(nodeName)
                        continue
        return nodes

    def __check_dependency_file(self):
        dep_file = os.path.join(self.projectPath, self.file_name)
        # 逐行读取文件
        with open(dep_file) as f:
            line = f.readline()
            while line:
                line = line.rstrip("\n")
                if len(line) == 0 or (
                        not line.startswith("+") and (not line.startswith("|")) and (not line.startswith("\\"))):
                    line = f.readline()
                    continue
                line = line.replace("\\", "+").replace("+---", "    ").replace("|", " ").replace("     ", "!")
                current_level = line.count("!")
                if current_level == 0:
                    line = f.readline()
                    continue
                last_parent = self.stack.pop()
                parent_level = last_parent.get_level()
                while not (current_level > parent_level):
                    last_parent = self.stack.pop()
                    parent_level = last_parent.get_level()
                line = line.replace("!", "").replace(" -> ", ":").replace(" (*)", "")
                buffer = line.split(":")
                tmp_length = len(buffer)
                if tmp_length > 2:
                    line = "%s:%s:%s" % (buffer[0], buffer[1], buffer[-1])
                if line in self.__node_set:
                    for node in self.allNode:
                        if node.value == line:
                            self.__update_node(node, last_parent)
                            break
                else:
                    node = TreeNode(line)
                    self.__update_node(node, last_parent)
                    self.__node_set.add(node.value)
                    self.allNode.append(node)

                node.add_parent(last_parent)
                last_parent.add_child(node)
                self.stack.append(last_parent)
                self.stack.append(node)
                line = f.readline()

    # 更新依赖关系
    @staticmethod
    def __update_node(node, parent):
        node.add_parent(parent)
        parent.add_child(node)

    """
    # 获取输入的多个aar依赖：该方法是要统计系列依赖比如fresco，animated-gif，webpsupport，animated-webp
    方法步骤：
        遍历输入的节点，将该节点的依赖树记录到result set中
        copy一份des set
        遍历该result set，检查每个节点的父节点是否仅在这个des set中
        在-->保留该节点，否则将该节点不是独有依赖，从des set中移除
        经过一次遍历后，该des set即为结果set
    """

    def __get_array_node(self, array):
        input_set = set()
        result = set()
        # 遍历输入的aar列表
        for s in array:
            n = self.__find_node_by_name(s)
            if n is None:
                print("暂无该依赖节点%s" % s)
                continue
            input_set.add(n)
            result.add(n)
            self.__add_children_node(n, result)
        # copy依赖的节点,作为结果set
        des = result.copy()
        for rNode in result:
            if rNode in input_set or 1 == len(rNode.parents):
                continue
            # 移除support库
            for p in rNode.parents:
                if p not in des:
                    des.remove(rNode)
                    break
        return des

    def get_input_aar(self, target_aar):
        if self.__check_aar_in_export(target_aar):
            print("不支持【%s】该类型的库统计！" % target_aar)
            return []
        array = [target_aar.lstrip(" ").rstrip(" ")]
        aars = self.__get_array_node(array)
        result = []
        for aar in aars:
            if self.__check_aar_in_export(aar.value):
                continue
            result.append(aar.value)
        return result

    # 校验传入的aar是否在去除列表中
    def __check_aar_in_export(self, aar_name):
        result = False
        for s in self.exportArr:
            if aar_name.startswith(s):
                result = True
                break
        return result

    # 遍历所有节点，记录在set中
    def __add_children_node(self, node, node_set):
        if len(node.children) == 0:
            node_set.add(node)
            return
        for child in node.children:
            node_set.add(child)
            self.__add_children_node(child, node_set)

    # 根据名称获取依赖节点
    def __find_node_by_name(self, node_name):
        node = None
        for n in self.allNode:
            if n.value.find(node_name) != -1:
                node = n
                break
        return node


class AarCache:
    # 记录传入的aar本地缓存路径
    targetAarPath = ""
    # gradle本地目录
    gradleUserHome = ""
    __envMap = os.environ

    def __init__(self):
        # 先检查是否将路径写在环境变量中
        gradle_home = self.__envMap.get("GRADLE_USER_HOME")
        if gradle_home is None or not os.path.exists(gradle_home):
            # 查看默认路径 ~/user/.gradle
            gradle_home = os.path.join(self.__envMap.get('HOME'), ".gradle")
        self.gradleUserHome = os.path.join(gradle_home, "caches", "modules-2", "files-2.1")

    # 获取率AAR
    def get_aar_file(self, aar_name):
        aar_info = aar_name.split(":")
        aar_path = os.path.join(self.gradleUserHome, aar_info[0], aar_info[1], aar_info[2])
        # print(aarPath)
        if not os.path.exists(aar_path):
            print("aar 本地缓存不存在")
            return False
        aar_file = self.__get_aar_file_(aar_path)
        self.targetAarPath = aar_file
        return aar_file and os.path.exists(aar_file)

    @staticmethod
    def __get_aar_file_(file):
        for root, dirs, files in os.walk(file, topdown=False):
            for name in files:
                if name.endswith(".aar"):
                    return os.path.join(root, name)


class Compile:
    def __init__(self, output_project_path):
        self.outputProjectPath = output_project_path

    def new_module(self, app_dirs):
        compile_sdk_version = ""
        build_tools_version = ""
        # settings.gradle
        settings = os.path.join(self.outputProjectPath, "settings.gradle")
        with open(settings, 'a+') as f:
            f.write("\ninclude ':zucker'")
        # app build.gradle
        regex = re.compile(r'dependencies([\s]*){')
        STATEMENT = "    implementation project(':zucker')\n"
        for dir in app_dirs:
            lines = []
            gradle_file = os.path.join(self.outputProjectPath, dir, "build.gradle")
            with open(gradle_file, 'r') as f:
                has_found_dependencies = False
                bracket_count = 0
                for line in f.readlines():
                    lines.append(line)
                    if line.lstrip().startswith("//"):
                        pass
                    if has_found_dependencies:
                        for index, c in enumerate(line):
                            if c == '{':
                                bracket_count += 1
                            elif c == '}':
                                bracket_count -= 1
                        if bracket_count < 0:
                            lines.remove(STATEMENT)
                            has_found_dependencies = False
                            bracket_count = 0
                    if "compileSdkVersion" in line:
                        compile_sdk_version = line
                    elif "buildToolsVersion" in line:
                        build_tools_version = line
                    elif regex.search(line):
                        has_found_dependencies = True
                        bracket_count += 1
                        lines.append(STATEMENT)
            with open(gradle_file, "w") as f:
                f.writelines(lines)
                f.close()
        # zucker dir
        zucker = os.path.join(self.outputProjectPath, "zucker")
        if not Path(zucker).exists():
            os.mkdir(zucker)
        # src dir
        src = os.path.join(zucker, "src")
        if not Path(src).exists():
            os.mkdir(src)
        # zucker main
        main = os.path.join(src, "main")
        if not Path(main).exists():
            os.mkdir(main)
        # AndroidManifest
        manifest = os.path.join(main, "AndroidManifest.xml")
        with open(manifest, 'w') as f:
            f.write("<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\" package=\"com.zucker\" />")
        # project build.gradle
        build = os.path.join(zucker, "build.gradle")
        with open(build, 'w') as f:
            f.write("apply plugin: 'com.android.library'\n\n")
            f.write("android {\n")
            f.write(compile_sdk_version + "\n")
            f.write(build_tools_version + "\n")
            f.write("}\n\n")
            f.write("dependencies {\n\n}")
        return main

    def clear_flavors(self, app_dirs):
        self.__clear_bucket_content('productFlavors', app_dirs)

    def insert_script(self, app_dirs):
        PATH = self.outputProjectPath
        for targetFile in app_dirs:
            package_size_path = os.path.join(PATH, targetFile, "zucker.txt")
            open(package_size_path, 'w')
            gradle_file = os.path.join(PATH, targetFile, 'build.gradle')
            with open(gradle_file, 'a+') as f:
                f.write("\n")
                f.write("android.applicationVariants.all { variant ->\n")
                f.write("   variant.outputs.all { output ->\n")
                f.write("       if (output.outputFileName.contains('debug.apk')) {\n")
                f.write("           Task assembleDebug = tasks.getByName('assembleDebug')\n")
                f.write("           File file = output.outputFile\n")
                f.write("           assembleDebug.doLast {\n")
                f.write("               def apkSize = file.length().toString()\n")
                f.write("               print('ApkSize: '+apkSize)\n")
                f.write("               def packageSizeFile = new File(\"" + package_size_path + "\")\n")
                f.write("               packageSizeFile.withWriter { writer ->\n")
                f.write("                     writer.write(apkSize)\n")
                f.write("               }\n")
                f.write("           }\n")
                f.write("       }\n")
                f.write("   }\n")
                f.write("}\n\n")

    def find_app_dirs(self):
        app_dirs = []
        PATH = self.outputProjectPath
        dir_list = [x for x in os.listdir(PATH) if
                    os.path.isdir(os.path.join(PATH, x)) and not x.startswith('.') and not x == 'gradle']
        for targetFile in dir_list:
            gradle_file = os.path.join(PATH, targetFile, 'build.gradle')
            if os.path.isfile(gradle_file):
                with open(gradle_file) as f:
                    for index, line in enumerate(f.readlines()):
                        if "apply plugin: 'com.android.application'" in line:
                            app_dirs.append(targetFile)
                            break
        return app_dirs

    def __clear_bucket_content(self, TAG, appDirs):
        PATH = self.outputProjectPath
        for targetFile in appDirs:
            gradle_file = os.path.join(PATH, targetFile, 'build.gradle')
            with open(gradle_file, 'r') as f:
                tag_lines = []
                has_find_tag = False
                has_find_start_tag = False
                has_find_end_tag = False
                bracket_count = 0
                for line in f.readlines():
                    if line.lstrip().startswith("//"):
                        tag_lines.append(line)
                        continue
                    if not has_find_tag:
                        index = line.find(TAG)
                        if index >= 0:
                            has_find_tag = True
                            start_index = 0
                            end_index = len(line)
                            for index, c in enumerate(line):
                                if c == '{':
                                    if not has_find_start_tag:
                                        has_find_start_tag = True
                                        start_index = index + 1
                                    bracket_count += 1
                                elif c == '}':
                                    bracket_count -= 1
                                if has_find_start_tag and bracket_count == 0:
                                    has_find_end_tag = True
                                    end_index = index
                                    break
                            if has_find_end_tag:
                                tag_lines.append(line[0:start_index] + line[end_index:len(line)])
                            else:
                                if has_find_start_tag:
                                    tag_lines.append(line[0:start_index] + "\n")
                                else:
                                    tag_lines.append(line)
                    if has_find_tag and not has_find_end_tag:
                        start_index = -1
                        end_index = len(line)
                        for index, c in enumerate(line):
                            if c == '{':
                                if not has_find_start_tag:
                                    has_find_start_tag = True
                                    start_index = index + 1
                                bracket_count += 1
                            elif c == '}':
                                bracket_count -= 1
                            if has_find_start_tag and bracket_count == 0:
                                has_find_end_tag = True
                                end_index = index
                                break
                        if has_find_start_tag:
                            linebreak = ""
                            if start_index >= 0:
                                linebreak = "\n"
                            else:
                                start_index = 0
                            if has_find_end_tag:
                                tag_lines.append(line[0:start_index] + linebreak + "    " + line[end_index:len(line)])
                            else:
                                tag_lines.append(line[0:start_index] + linebreak)
                        else:
                            tag_lines.append(line)
                    if has_find_tag and has_find_end_tag:
                        tag_lines.append(line)
                    if not has_find_tag and not has_find_end_tag:
                        tag_lines.append(line)
                if has_find_tag:
                    fd = open(gradle_file, "w")
                    fd.writelines(tag_lines)
                    fd.close()

    def compile(self):
        command = "cd " + self.outputProjectPath + "\n"
        command += "chmod +x gradlew" + "\n"
        command += "./gradlew clean" + "\n"
        command += "./gradlew assembleDebug"
        subprocess.call(command, shell=True)


class MockCache:
    zucker_res_size = 0

    def __init__(self, origin_aar_cache_path, target_main_src_path):
        # 复制文件
        self.originAarCachePath = origin_aar_cache_path
        self.targetMainSrcPath = target_main_src_path
        self.mockAarCachePath = origin_aar_cache_path.replace(".aar", "-origin.zip")
        self.mockAarOriginPath = origin_aar_cache_path.replace(".aar", "-origin.aar")

    def mock_cache(self):
        copyfile(self.originAarCachePath, self.mockAarCachePath)
        copyfile(self.originAarCachePath, self.mockAarOriginPath)

        # 解压
        unzip_file = os.path.dirname(self.originAarCachePath) + "/" + (
            os.path.basename(self.originAarCachePath)).replace(".aar", "")
        file_zip = zipfile.ZipFile(self.mockAarCachePath, 'r')
        for file in file_zip.namelist():
            file_zip.extract(file, unzip_file)
        file_zip.close()

        self._copy_mock_file(unzip_file, self.targetMainSrcPath)
        # 基础Mock
        for root, dirs, files in os.walk(os.path.dirname(self.targetMainSrcPath + "/res"), topdown=False):
            for name in files:
                if name.startswith('values') and name.endswith('.xml'):
                    pass
                elif name in ('AndroidManifest.xml'):
                    pass
                elif ('layout' in root) and name.endswith('.xml'):
                    mypath = os.path.join(root, name)
                    fd = open(mypath, "w")
                    fd.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>")
                    fd.write("<FrameLayout/>")
                    fd.close()
                elif ('drawable' in root) and name.endswith('.xml'):
                    mypath = os.path.join(root, name)
                    fd = open(mypath, "w")
                    fd.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>")
                    fd.write("<selector/>")
                    fd.close()
                elif ('drawable' in root) and name.endswith('.9.png'):
                    pass
                elif ('mipmap' in root) and name.endswith('.9.png'):
                    pass
                elif ('anim' in root) and name.endswith('.xml'):
                    mypath = os.path.join(root, name)
                    fd = open(mypath, "w")
                    fd.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>")
                    fd.write("<set/>")
                    fd.close()
                elif ('color' in root) and name.endswith('.xml'):
                    mypath = os.path.join(root, name)
                    fd = open(mypath, "w")
                    fd.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>")
                    fd.write("<selector/>")
                    fd.close()
                elif ('xml' in root) and name.endswith('.xml'):
                    mypath = os.path.join(root, name)
                    fd = open(mypath, "w")
                    fd.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>")
                    fd.write("<paths/>")
                    fd.close()
                else:
                    mypath = os.path.join(root, name)
                    fd = open(mypath, "w")
                    fd.writelines([])
                    fd.close()

        # 遍历文件，并删除  os.path.join(path, file)
        white_list = ["classes.jar"]
        dirs = os.listdir(unzip_file)
        for root, dirs, files in os.walk(unzip_file, topdown=False):
            for name in files:
                if name in white_list:
                    pass
                else:
                    os.remove(os.path.join(root, name))
        # 删除原有AAR
        for root, dirs, files in os.walk(os.path.dirname(self.originAarCachePath), topdown=False):
            for name in files:
                if name in os.path.basename(self.originAarCachePath):
                    os.remove(os.path.join(root, name))

        # 计算zucker库里面res的文件大小
        self.zucker_res_size = self._get_dir_size(os.path.dirname(self.targetMainSrcPath + "/res"))
        # 压缩Mock的File
        self._zip_mock_file(unzip_file)

    @staticmethod
    def _get_dir_size(path):
        # 计算指定的路径下的所有文件的大小
        if os.path.isdir(path):
            file_size, dir_list = 0, [path]
            while dir_list:
                path = dir_list.pop()
                dirs = os.listdir(path)
                for name in dirs:
                    file_path = os.path.join(path, name)
                    if os.path.isfile(file_path):
                        file_size += os.path.getsize(file_path)
                    else:
                        dir_list.append(file_path)
            return file_size
        elif os.path.isfile(path):
            return os.path.getsize(path)
        else:
            print('找不到%s文件' % path)

    def _copytree(self, src, dst, symlinks=False, ignore=None, copy_function=shutil.copy2):
        names = os.listdir(src)
        if ignore is not None:
            ignored_names = ignore(src, names)
        else:
            ignored_names = set()
        if not os.path.exists(dst):
            os.makedirs(dst)
        errors = []
        for name in names:
            if name in ignored_names:
                continue
            srcname = os.path.join(src, name)
            dstname = os.path.join(dst, name)
            try:
                if os.path.islink(srcname):
                    linkto = os.readlink(srcname)
                    if symlinks:
                        # We can't just leave it to `copy_function` because legacy
                        # code with a custom `copy_function` may rely on copytree
                        # doing the right thing.
                        os.symlink(linkto, dstname)
                        shutil.copystat(srcname, dstname, follow_symlinks=not symlinks)
                    else:
                        # ignore dangling symlink if the flag is on
                        if not os.path.exists(linkto) and False:
                            continue
                        # otherwise let the copy occurs. copy2 will raise an error
                        if os.path.isdir(srcname):
                            self._copytree(srcname, dstname, symlinks, ignore,
                                           copy_function)
                        else:
                            copy_function(srcname, dstname)
                elif os.path.isdir(srcname):
                    self._copytree(srcname, dstname, symlinks, ignore, copy_function)
                else:
                    # Will raise a SpecialFileError for unsupported file types
                    copy_function(srcname, dstname)
            # catch the Error from the recursive copytree so that we can
            # continue with other files
            except shutil.Error as err:
                errors.extend(err.args[0])
            except OSError as why:
                errors.append((srcname, dstname, str(why)))
        try:
            shutil.copystat(src, dst)
        except OSError as why:
            # Copying file access times may fail on Windows
            if getattr(why, 'winerror', None) is None:
                errors.append((src, dst, str(why)))
        if errors:
            raise shutil.Error(errors)
        return dst

    def _copy_mock_file(self, origin_path, target_main_src_path):
        origin_path = origin_path + "/res"
        if os.path.exists(origin_path):
            self._copytree(origin_path, target_main_src_path + "/res")
        elif not os.path.exists(target_main_src_path + "/res"):
            os.makedirs(target_main_src_path + "/res")

    @staticmethod
    def _zip_mock_file(start_dir):
        start_dir = start_dir
        file_news = start_dir + '.aar'

        z = zipfile.ZipFile(file_news, 'w', zipfile.ZIP_DEFLATED)
        for dir_path, dir_names, file_names in os.walk(start_dir):
            f_path = dir_path.replace(start_dir, '')
            f_path = f_path and f_path + os.sep or ''
            for filename in file_names:
                z.write(os.path.join(dir_path, filename), f_path + filename)
        z.close()
        return file_news

    @staticmethod
    def add_configurations(aar, output_project_path, app_dir):
        aars = aar.split(":")
        name = aars[1] + "-" + aars[2]
        sub_path = os.path.join(output_project_path, app_dir)

        build_gradle = sub_path + "/build.gradle"
        if os.path.exists(build_gradle):
            # 先读文件
            configurations = open(build_gradle, 'r')
            content = configurations.read()
            post = content.find("configurations {")
            if post != -1:
                configurations = open(build_gradle, 'w')
                content = content[:post + len("configurations {")] + "\n" + "all*.exclude group: \'" + aars[
                    0] + "\'" + " ,module: " + "\'" + aars[1] + "\'\n" + content[post + len("configurations {"):]
                configurations.write(content)
            else:
                configurations = open(build_gradle, 'a+')
                configurations.write("configurations {")
                configurations.write("\n")
                configurations.write("all*.exclude group: \'" + aars[0] + "\'" + " ,module: " + "\'" + aars[1] + "\'")
                configurations.write("\n")
                configurations.write("}")
            configurations.close()


class RevertCache:
    # 回滚修改的Cache目标AAR
    def __init__(self, origin_aar_cache_path):
        self.originAarCachePath = origin_aar_cache_path

    def revert(self):
        file_name = os.path.dirname(self.originAarCachePath)
        dirs = os.listdir(file_name)
        for root, dirs, files in os.walk(file_name, topdown=False):
            for name in files:
                if name.endswith("-origin.aar"):
                    pass
                else:
                    os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))

        for root, dirs, files in os.walk(file_name, topdown=False):
            for name in files:
                if name.endswith("-origin.aar"):
                    new_name = copy.deepcopy(name)
                    new_name = new_name.replace("-origin.aar", ".aar")
                    os.rename(root + "/" + name, root + "/" + new_name)


class PackageSize:
    # 统计大小，并输出最终结果
    @staticmethod
    def get_result(base_output_project_path, aar_output_project_path, app_dir, zucker_res_size):
        base_pack_size = 0
        aar_pack_size = 0
        base_pack_size_path = os.path.join(base_output_project_path, app_dir, "zucker.txt")
        aar_pack_size_path = os.path.join(aar_output_project_path, app_dir, "zucker.txt")
        with open(base_pack_size_path) as f:
            for line in f.readlines():
                base_pack_size = line
                print("基础包大小(basePackSize,单位Byte): " + line)
                break
        with open(aar_pack_size_path) as f:
            for line in f.readlines():
                aar_pack_size = line
                aar_pack_size = int(aar_pack_size) - (int(zucker_res_size) * 2)
                print("替换后的APK大小(aarPackSize,单位Byte): " + str(aar_pack_size))
                break
        aar_size = int(base_pack_size) - int(aar_pack_size)
        print("AAR大小(aarSize,单位Byte): " + str(aar_size))


if __name__ == '__main__':
    sys.argv.append("ZuckerDemo")
    # 工程文件夹名称
    projectName = sys.argv[1]
    # 当前目录
    currentPath = os.getcwd()
    # 输出目录
    outputPath = os.path.join(currentPath, "output")
    # 资源大小
    zuckerResSize = ""
    # 是否找到缓存
    isCacheExist = False

    # 基础包：克隆、打包流程======================================
    # 基础包AAR工程目录
    baseOutputProjectPath = os.path.join(outputPath, projectName + "_BASE")
    if not os.path.exists(baseOutputProjectPath):
        # 克隆工程
        cloneBaseProject = CloneProject()
        cloneBaseProject.clone(currentPath, outputPath, projectName, projectName + "_BASE")
        print("cloneBaseProject DONE")
        # 编译工程
        baseCompile = Compile(baseOutputProjectPath)
        baseAppDirs = baseCompile.find_app_dirs()
        print("findBaseAppDirs DONE")
        baseCompile.clear_flavors(baseAppDirs)
        print("clearBaseFlavors DONE")
        baseCompile.insert_script(baseAppDirs)
        print("insertBaseScript DONE")
        baseCompile.compile()

    # AAR：克隆、依赖、mock、打包流程======================================
    # AAR工程目录
    outputProjectPath = os.path.join(outputPath, projectName + "_AAR")
    # 如果已经存在，则删除
    if os.path.exists(outputProjectPath):
        shutil.rmtree(outputProjectPath, True)
    # 克隆工程
    cloneProject = CloneProject()
    cloneProject.clone(currentPath, outputPath, projectName, projectName + "_AAR")
    print("cloneAARProject DONE")
    # 编译工程
    compile = Compile(outputProjectPath)
    appDirs = compile.find_app_dirs()
    print("findAARAppDirs DONE")
    zuckerModuleMainDir = compile.new_module(appDirs)
    print("newModule DONE: " + zuckerModuleMainDir)
    compile.clear_flavors(appDirs)
    print("clearAARFlavors DONE")
    compile.insert_script(appDirs)
    print("insertAARScript DONE")

    # 遍历工程下依赖的所有AAR
    for appdir in appDirs:
        dependency = Dependency(outputProjectPath, appdir)
        aars = dependency.get_top_level_aars()
        for aar in aars:
            print(aar)
        target_aar = input("输入AAR名称及版本，格式xxx.xxx:xxx:xxx:")
        result_aars = dependency.get_input_aar(target_aar)
        print("输出AAR:")
        print(result_aars)

        targetAarArray = []
        for aar in result_aars:
            aar_cache = AarCache()
            if aar_cache.get_aar_file(aar):
                print(aar_cache.targetAarPath)
                mockCache = MockCache(aar_cache.targetAarPath, zuckerModuleMainDir)
                mockCache.mock_cache()
                mockCache.add_configurations(aar, outputProjectPath, appdir)
                zuckerResSize = mockCache.zucker_res_size
                targetAarArray.append(aar_cache.targetAarPath)
                isCacheExist = True
            else:
                isCacheExist = False

        if isCacheExist:
            compile.compile()
            print("compile DONE")

            # 将修改的AAR进行回滚
            for path in targetAarArray:
                revertCache = RevertCache(path)
                revertCache.revert()

            # 统计大小并输出
            packSize = PackageSize()
            packSize.get_result(baseOutputProjectPath, compile.outputProjectPath, appdir, zuckerResSize)
        else:
            print("缓存aar未找到，请重新尝试")
        # break
