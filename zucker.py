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
import urllib
import urllib.request
import json
import zipfile
import argparse
import distutils.spawn
import datetime
import time
import ftplib
import copy
from pathlib import Path


class CloneProject:
    def clone(self, current_path, outputPath, target_project_name, output_project_name):
        self.target_project_name = target_project_name
        # 如果output目录不存在，则创建文件夹
        if not os.path.exists(outputPath):
            os.mkdir(outputPath)
        self.__copydir(current_path, outputPath, output_project_name, 0)

    # 拷贝文件夹
    def __copydir(self, source_dir, target_dir, target, index):
        # 源文件夹
        dir = os.path.join(source_dir, target)
        if index == 0:
            dir = os.path.join(source_dir, self.target_project_name)
        else:
            dir = os.path.join(source_dir, target)
        # 源文件夹下的文件列表
        files = os.listdir(dir)
        # 目标文件夹
        targetdir = os.path.join(target_dir, target)
        if not os.path.exists(targetdir):
            os.mkdir(targetdir)
        if index == 0:
            self.fileSize = 0
            for dirpath, dirnames, filenames in os.walk(dir):
                for file in filenames:
                    self.fileSize = self.fileSize + 1
            self.count = 0
        for f in files:
            sourcefile = os.path.join(dir, f)
            targetfile = os.path.join(targetdir, f)
            if os.path.isdir(sourcefile):
                index += 1
                self.__copydir(dir, targetdir, f, index)
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

    def addChild(self, node):
        self.children.add(node)

    def addParent(self, node):
        self.parent = node
        self.parents.add(node)

    def isRoot(self):
        return len(self.parents) == 0 or self.parent is None

    def getLevel(self):
        if self.isRoot():
            return 0
        return self.parent.getLevel() + 1


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

    def __init__(self, outputProjectPath, appdir):
        self.file_name = "dependency_" + appdir + ".txt"
        self.projectPath = outputProjectPath
        self.appDir = appdir

    def gettoplevelaars(self):
        self.rootNode = TreeNode(self.appDir)
        self.stack.append(self.rootNode)
        self.allNode.append(self.rootNode)
        # 执行gradle命令
        self.commend = (self.commend % self.appDir) + os.path.join(self.projectPath, self.file_name)
        # cd到工程目录下，才能正常的读取gradle命令
        self.commend = ("cd %s\nchmod +x gradlew\n" % self.projectPath) + self.commend
        subprocess.check_call(self.commend, shell=True)
        self.__checkDependencyFile()

        nodes = []
        for n in self.allNode:
            nodeName = n.value
            if len(n.parents) >= 1 and not self.__checkAARInExport(nodeName):
                for p in n.parents:
                    if p == self.rootNode:
                        nodes.append(nodeName)
                        continue
        return nodes

    def __checkDependencyFile(self):
        depFile = os.path.join(self.projectPath, self.file_name)
        # 逐行读取文件
        with open(depFile) as f:
            line = f.readline()
            while line:
                line = line.rstrip("\n")
                if len(line) == 0 or (
                        not line.startswith("+") and (not line.startswith("|")) and (not line.startswith("\\"))):
                    line = f.readline()
                    continue
                line = line.replace("\\", "+").replace("+---", "    ").replace("|", " ").replace("     ", "!")
                currentLevel = line.count("!")
                if currentLevel == 0:
                    line = f.readline()
                    continue
                lastParent = self.stack.pop()
                parentLevel = lastParent.getLevel()
                while not (currentLevel > parentLevel):
                    lastParent = self.stack.pop()
                    parentLevel = lastParent.getLevel()
                line = line.replace("!", "").replace(" -> ", ":").replace(" (*)", "")
                buffer = line.split(":")
                tmpLength = len(buffer)
                if tmpLength > 2:
                    line = "%s:%s:%s" % (buffer[0], buffer[1], buffer[-1])
                if line in self.__node_set:
                    for node in self.allNode:
                        if node.value == line:
                            self.__update_node(node, lastParent)
                            break
                else:
                    node = TreeNode(line)
                    self.__update_node(node, lastParent)
                    self.__node_set.add(node.value)
                    self.allNode.append(node)

                node.addParent(lastParent)
                lastParent.addChild(node)
                self.stack.append(lastParent)
                self.stack.append(node)
                line = f.readline()

    # 更新依赖关系
    def __update_node(self, node, parent):
        node.addParent(parent)
        parent.addChild(node)

    """
    # 获取输入的多个aar依赖：该方法是要统计系列依赖比如fresco，animated-gif，webpsupport，animated-webp
    方法步骤：
        遍历输入的节点，将该节点的依赖树记录到result set中
        copy一份des set
        遍历该result set，检查每个节点的父节点是否仅在这个des set中
        在-->保留该节点，否则将该节点不是独有依赖，从des set中移除
        经过一次遍历后，该des set即为结果set
    """

    def __getArrayNode(self, array):
        inputSet = set()
        result = set()
        # 遍历输入的aar列表
        for s in array:
            n = self.__findNodeByName(s)
            if n is None:
                print("暂无该依赖节点%s" % s)
                continue
            inputSet.add(n)
            result.add(n)
            self.__add_children_node(n, result)
        # copy依赖的节点,作为结果set
        des = result.copy()
        for rNode in result:
            if rNode in inputSet or 1 == len(rNode.parents):
                continue
            # 移除support库
            for p in rNode.parents:
                if p not in des:
                    des.remove(rNode)
                    break
        return des

    def getInputAAR(self, target_aar):
        if self.__checkAARInExport(target_aar):
            print("不支持【%s】该类型的库统计！" % target_aar)
            return []
        array = [target_aar.lstrip(" ").rstrip(" ")]
        aars = self.__getArrayNode(array)
        result = []
        for aar in aars:
            if self.__checkAARInExport(aar.value):
                continue
            result.append(aar.value)
        return result

    # 校验传入的aar是否在去除列表中
    def __checkAARInExport(self, aar_name):
        isIn = False
        for s in self.exportArr:
            if aar_name.startswith(s):
                isIn = True
                break
        return isIn

    # 遍历所有节点，记录在set中
    def __add_children_node(self, node, nodeset):
        if len(node.children) == 0:
            nodeset.add(node)
            return
        for child in node.children:
            nodeset.add(child)
            self.__add_children_node(child, nodeset)

    # 根据名称获取依赖节点
    def __findNodeByName(self, node_name):
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
        gradleHome = self.__envMap.get("GRADLE_USER_HOME")
        if gradleHome is None or not os.path.exists(gradleHome):
            # 查看默认路径 ~/user/.gradle
            gradleHome = os.path.join(self.__envMap.get('HOME'), ".gradle")
        self.gradleUserHome = os.path.join(gradleHome, "caches", "modules-2", "files-2.1")

    # 获取率AAR
    def getAARFile(self, aar_name):
        aarInfo = aar_name.split(":")
        aarPath = os.path.join(self.gradleUserHome, aarInfo[0], aarInfo[1], aarInfo[2])
        # print(aarPath)
        if not os.path.exists(aarPath):
            print("aar 本地缓存不存在")
            return False
        aarFile = self.__get_aar_file_(aarPath)
        self.targetAarPath = aarFile
        return aarFile and os.path.exists(aarFile)

    def __get_aar_file_(self, file):
        for root, dirs, files in os.walk(file, topdown=False):
            for name in files:
                if name.endswith(".aar"):
                    return os.path.join(root, name)

class Compile:
    def __init__(self, output_project_path):
        self.outputProjectPath = output_project_path

    def newmodule(self, app_dirs):
        compileSdkVersion = ""
        buildToolsVersion = ""
        # settings.gradle
        settings = os.path.join(self.outputProjectPath, "settings.gradle")
        with open(settings, 'a+') as f:
            f.write("\ninclude ':zucker'")
        # app build.gradle
        regex = re.compile(r'dependencies([\s]*){')
        STATEMENT = "    implementation project(':zucker')\n"
        for dir in app_dirs:
            lines = []
            gradleFile = os.path.join(self.outputProjectPath, dir, "build.gradle")
            with open(gradleFile, 'r') as f:
                hasFoundDependencies = False
                bracketCount = 0
                for line in f.readlines():
                    lines.append(line)
                    if line.lstrip().startswith("//"):
                        pass
                    if hasFoundDependencies == True:
                        for index, c in enumerate(line):
                            if c == '{':
                                bracketCount += 1
                            elif c == '}':
                                bracketCount -= 1
                        if bracketCount < 0:
                            lines.remove(STATEMENT)
                            hasFoundDependencies = False
                            bracketCount = 0
                    if "compileSdkVersion" in line:
                        compileSdkVersion = line
                    elif "buildToolsVersion" in line:
                        buildToolsVersion = line
                    elif regex.search(line):
                        hasFoundDependencies = True
                        bracketCount += 1
                        lines.append(STATEMENT)
            with open(gradleFile, "w") as f:
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
            f.write(compileSdkVersion + "\n")
            f.write(buildToolsVersion + "\n")
            f.write("}\n\n")
            f.write("dependencies {\n\n}")
        return main

    def clearflavors(self, app_dirs):
        self.__clearbucketcontent('productFlavors', app_dirs)

    def insertscript(self, app_dirs):
        PATH = self.outputProjectPath
        for targetFile in app_dirs:
            packageSizePath = os.path.join(PATH, targetFile, "zucker.txt")
            open(packageSizePath, 'w')
            gradleFile = os.path.join(PATH, targetFile, 'build.gradle')
            with open(gradleFile, 'a+') as f:
                f.write("\n")
                f.write("android.applicationVariants.all { variant ->\n")
                f.write("   variant.outputs.all { output ->\n")
                f.write("       if (output.outputFileName.contains('debug.apk')) {\n")
                f.write("           Task assembleDebug = tasks.getByName('assembleDebug')\n")
                f.write("           File file = output.outputFile\n")
                f.write("           assembleDebug.doLast {\n")
                f.write("               def apkSize = file.length().toString()\n")
                f.write("               print('ApkSize: '+apkSize)\n")
                f.write("               def packageSizeFile = new File(\"" + (packageSizePath) + "\")\n")
                f.write("               packageSizeFile.withWriter { writer ->\n")
                f.write("                     writer.write(apkSize)\n")
                f.write("               }\n")
                f.write("           }\n")
                f.write("       }\n")
                f.write("   }\n")
                f.write("}\n\n")

    def findappdirs(self):
        appDirs = []
        PATH = self.outputProjectPath
        dirList = [x for x in os.listdir(PATH) if
                   os.path.isdir(os.path.join(PATH, x)) and not x.startswith('.') and not x == 'gradle']
        for targetFile in dirList:
            gradleFile = os.path.join(PATH, targetFile, 'build.gradle')
            if os.path.isfile(gradleFile):
                with open(gradleFile) as f:
                    for index, line in enumerate(f.readlines()):
                        if "apply plugin: 'com.android.application'" in line:
                            appDirs.append(targetFile)
                            break
        return appDirs

    def __clearbucketcontent(self, TAG, appDirs):
        PATH = self.outputProjectPath
        for targetFile in appDirs:
            gradleFile = os.path.join(PATH, targetFile, 'build.gradle')
            with open(gradleFile, 'r') as f:
                taglines = []
                hasFindTag = False
                hasFindStartTag = False
                hasFindEndTag = False
                bracketCount = 0
                for line in f.readlines():
                    if line.lstrip().startswith("//"):
                        taglines.append(line)
                        continue
                    if not hasFindTag:
                        index = line.find(TAG)
                        if index >= 0:
                            hasFindTag = True
                            startIndex = 0
                            endIndex = len(line)
                            for index, c in enumerate(line):
                                if c == '{':
                                    if not hasFindStartTag:
                                        hasFindStartTag = True
                                        startIndex = index + 1
                                    bracketCount += 1
                                elif c == '}':
                                    bracketCount -= 1
                                if hasFindStartTag and bracketCount == 0:
                                    hasFindEndTag = True
                                    endIndex = index
                                    break
                            if hasFindEndTag:
                                taglines.append(line[0:startIndex] + line[endIndex:len(line)])
                            else:
                                if hasFindStartTag:
                                    taglines.append(line[0:startIndex] + "\n")
                                else:
                                    taglines.append(line)
                    if hasFindTag and not hasFindEndTag:
                        startindex = -1
                        endindex = len(line)
                        for index, c in enumerate(line):
                            if c == '{':
                                if not hasFindStartTag:
                                    hasFindStartTag = True
                                    startindex = index + 1
                                bracketCount += 1
                            elif c == '}':
                                bracketCount -= 1
                            if hasFindStartTag and bracketCount == 0:
                                hasFindEndTag = True
                                endindex = index
                                break
                        if hasFindStartTag:
                            linebreak = ""
                            if startindex >= 0:
                                linebreak = "\n"
                            else:
                                startindex = 0
                            if hasFindEndTag:
                                taglines.append(line[0:startindex] + linebreak + "    " + line[endindex:len(line)])
                            else:
                                taglines.append(line[0:startindex] + linebreak)
                        else:
                            taglines.append(line)
                    if hasFindTag and hasFindEndTag:
                        taglines.append(line)
                    if not hasFindTag and not hasFindEndTag:
                        taglines.append(line)
                if hasFindTag:
                    fd = open(gradleFile, "w")
                    fd.writelines(taglines)
                    fd.close()

    def compile(self):
        command = "cd " + self.outputProjectPath + "\n"
        command += "chmod +x gradlew" + "\n"
        command += "./gradlew clean" + "\n"
        command += "./gradlew assembleDebug"
        subprocess.call(command, shell=True)


class MockCache:
    def __init__(self, originAarCachePath, targetMainSrcPath):
        # 复制文件
        self.originAarCachePath = originAarCachePath
        self.targetMainSrcPath = targetMainSrcPath
        self.mockAarCachePath = originAarCachePath.replace(".aar", "-origin.zip")
        self.mockAarOriginPath = originAarCachePath.replace(".aar", "-origin.aar")

    def mockCache(self):
        copyfile(self.originAarCachePath, self.mockAarCachePath)
        copyfile(self.originAarCachePath, self.mockAarOriginPath)

        # 解压
        unzipFile = os.path.dirname(self.originAarCachePath) + "/" + (os.path.basename(self.originAarCachePath)).replace(".aar","")
        file_zip = zipfile.ZipFile(self.mockAarCachePath, 'r')
        for file in file_zip.namelist():
            file_zip.extract(file, unzipFile)
        file_zip.close()

        self._copyMockFile(unzipFile, self.targetMainSrcPath)
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
                    fd.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>");
                    fd.write("<FrameLayout/>");
                    fd.close()
                elif ('drawable' in root) and name.endswith('.xml'):
                    mypath = os.path.join(root, name)
                    fd = open(mypath, "w")
                    fd.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>");
                    fd.write("<selector/>");
                    fd.close()
                elif ('drawable' in root) and name.endswith('.9.png'):
                    pass
                elif ('mipmap' in root) and name.endswith('.9.png'):
                    pass
                elif ('anim' in root) and name.endswith('.xml'):
                    mypath = os.path.join(root, name)
                    fd = open(mypath, "w")
                    fd.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>");
                    fd.write("<set/>");
                    fd.close()
                elif ('color' in root) and name.endswith('.xml'):
                    mypath = os.path.join(root, name)
                    fd = open(mypath, "w")
                    fd.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>");
                    fd.write("<selector/>");
                    fd.close()
                elif ('xml' in root) and name.endswith('.xml'):
                    mypath = os.path.join(root, name)
                    fd = open(mypath, "w")
                    fd.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>");
                    fd.write("<paths/>");
                    fd.close()
                else:
                    mypath = os.path.join(root, name)
                    fd = open(mypath, "w")
                    fd.writelines([])
                    fd.close()

        # 遍历文件，并删除  os.path.join(path, file)
        whiteList = ["classes.jar"]
        dirs = os.listdir(unzipFile)
        for root, dirs, files in os.walk(unzipFile, topdown=False):
            for name in files:
                if name in whiteList:
                    pass
                else:
                    os.remove(os.path.join(root, name))
        # 删除原有AAR
        for root, dirs, files in os.walk(os.path.dirname(self.originAarCachePath), topdown=False):
            for name in files:
                if name in os.path.basename(self.originAarCachePath):
                    os.remove(os.path.join(root, name))

        # 计算zucker库里面res的文件大小
        self.zuckerResSize = self._get_dirsize(os.path.dirname(self.targetMainSrcPath + "/res"))
        # 压缩Mock的File
        self._zipMockFile(unzipFile)

    def _get_dirsize(self, path):
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

    def _copyMockFile(self, originPath, targetMainSrcPath):
        originPath = originPath + "/res"
        if os.path.exists(originPath):
            self._copytree(originPath, targetMainSrcPath + "/res")
        elif not os.path.exists(targetMainSrcPath + "/res"):
            os.makedirs(targetMainSrcPath + "/res")

    def _zipMockFile(self, start_dir):
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

    def addConfigurations(self, aar, outputProjectPath, appdir):
        aars = aar.split(":")
        name = aars[1] + "-" + aars[2]
        subpath = os.path.join(outputProjectPath, appdir)

        buildGradle = subpath + "/build.gradle";
        if os.path.exists(buildGradle):
            # 先读文件
            configurations = open(buildGradle, 'r')
            content = configurations.read();
            post = content.find("configurations {")
            # all*.exclude group: 'com.wuba.wuxian.sdk', module: 'support-v4'
            if post != -1:
                configurations = open(buildGradle, 'w');
                content = content[:post + len("configurations {")] + "\n" + "all*.exclude group: \'" + aars[
                    0] + "\'" + " ,module: " + "\'" + aars[1] + "\'\n" + content[post + len("configurations {"):]
                configurations.write(content)
            else:
                configurations = open(buildGradle, 'a+');
                configurations.write("configurations {");
                configurations.write("\n");
                configurations.write("all*.exclude group: \'" + aars[0] + "\'" + " ,module: " + "\'" + aars[1] + "\'");
                configurations.write("\n");
                configurations.write("}");
            configurations.close();

class RevertCache:
    # 回滚修改的Cache目标AAR
    def __init__(self, originAarCachePath):
        self.originAarCachePath = originAarCachePath

    def revert(self):
        fileName = os.path.dirname(self.originAarCachePath)
        dirs = os.listdir(fileName)
        for root, dirs, files in os.walk(fileName, topdown=False):
            for name in files:
                if name.endswith("-origin.aar"):
                    pass
                else:
                    os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))

        for root, dirs, files in os.walk(fileName, topdown=False):
            for name in files:
                if name.endswith("-origin.aar"):
                    new_name = copy.deepcopy(name)
                    new_name = new_name.replace("-origin.aar", ".aar")
                    os.rename(root + "/" + name, root + "/" + new_name)

class PackageSize:
    # 统计大小，并输出最终结果
    def getresult(self, baseOutputProjectPath, aarOutputProjectPath, appdir, zuckerResSize):
        basePackSize = 0
        aarPackSize = 0
        basePackSizePath = os.path.join(baseOutputProjectPath, appdir, "zucker.txt")
        aarPackSizePath = os.path.join(aarOutputProjectPath, appdir, "zucker.txt")
        with open(basePackSizePath) as f:
            for line in f.readlines():
                basePackSize = line
                print("基础包大小(basePackSize,单位Byte): " + line)
                break
        with open(aarPackSizePath) as f:
            for line in f.readlines():
                aarPackSize = line
                aarPackSize = int(aarPackSize) - (int(zuckerResSize)*2)
                print("替换后的APK大小(aarPackSize,单位Byte): " + str(aarPackSize))
                break
        aarSize = int(basePackSize) - int(aarPackSize)
        print("AAR大小(aarSize,单位Byte): " + str(aarSize))


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
        baseAppDirs = baseCompile.findappdirs()
        print("findBaseAppDirs DONE")
        baseCompile.clearflavors(baseAppDirs)
        print("clearBaseFlavors DONE")
        baseCompile.insertscript(baseAppDirs)
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
    appDirs = compile.findappdirs()
    print("findAARAppDirs DONE")
    zuckerModuleMainDir = compile.newmodule(appDirs)
    print("newModule DONE: " + zuckerModuleMainDir)
    compile.clearflavors(appDirs)
    print("clearAARFlavors DONE")
    compile.insertscript(appDirs)
    print("insertAARScript DONE")

    # 遍历工程下依赖的所有AAR
    for appdir in appDirs:
        dependency = Dependency(outputProjectPath, appdir)
        aars = dependency.gettoplevelaars()
        for aar in aars:
            print(aar)
        targetaar = input("输入AAR名称及版本，格式xxx.xxx:xxx:xxx:")
        resultaars = dependency.getInputAAR(targetaar)
        print("输出AAR:")
        print(resultaars)

        targetAarArray = []
        for aar in resultaars:
            aarcache = AarCache()
            if aarcache.getAARFile(aar):
                print(aarcache.targetAarPath)
                mockCache = MockCache(aarcache.targetAarPath, zuckerModuleMainDir)
                mockCache.mockCache()
                mockCache.addConfigurations(aar, outputProjectPath, appdir)
                zuckerResSize = mockCache.zuckerResSize
                targetAarArray.append(aarcache.targetAarPath)
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
            packSize.getresult(baseOutputProjectPath, compile.outputProjectPath, appdir, zuckerResSize)
        else:
            print("缓存aar未找到，请重新尝试")
        # break
