# Zucker：一个简单无侵害计算AAR独有大小的工具
## Zucker: An easier way to automatically calculate the size of AAR in apk.
[英文文档](README_EN.md)

> AAR独立大小和被引入到工程后打包后占用的大小是不一样的，这个有经验的开发者都应该了解。AAR独立大小一目了然，但是怎么计算AAR在APK中的独立占有大小（独有大小）呢？Zucker就此开源给出了一份答案。

## 依赖环境
- Python 3.0+
- Android编译环境

## 开始使用
### Demo工程测试
1. 克隆本工程
2. 终端cd到本工程下的src目录
3. 执行python脚本：python3 zucker.py Sample
4. 根据终端列出的AAR列表，选择一个目标AAR输入得到结果

### 项目工程测试
1. 将zucker.py脚本放置在需要测试工程的同级目录
2. 同[Demo工程测试]步骤2
3. 同[Demo工程测试]步骤3：python3 zucker.py [targetProjectName](Android工程名)
4. 同[Demo工程测试]步骤4

### 注意事项
1. 确保目标工程在不依赖Zucker脚本的前提下可以正常编译
2. 编译时使用`gradlew`命令，以保证采用了项目的`gradle`配置
3. 首次运行时间较长，请耐心等待...

```
./gradlew build

```
![配置初始化](./imgs/sample_clone.png)

脚本会自动执行，获取项目中的依赖关系并输出一级节点，可以选择目标节点进行AAR大小计算。

![AAR列表](./imgs/sample_aar.png)

最后经过打包后，AAR大小就会显示在终端上。

![AAR测量结果](./imgs/sample_aar_size.png)

> 建议先在本项目的`sample工程`进行测试，具体流程见工程[README](Sample/README.md)


## 常见问题处理
 -  暂不支持工程依赖类型的测量 `implementation project(':xxx')` 
 -  在build过程中发生报错：Could not get resource 'https://jcenter.bintray.com/com/google/guava/guava/27.0.1-jre/guava-27.0.1-jre.jar'
 
 解决办法：使用阿里云镜像，重新进行下载；修改build.gradle中的buildscript和allprojects的jcenter，添加url 'https://maven.aliyun.com/repository/jcenter'即可。

## 贡献代码
详见 [CONTRIBUTING](CONTRIBUTING.rst)


## 许可协议


 Copyright Zucker

 Licensed under the Apache License, Version 2.0 (the "License"); you may
 not use this file except in compliance with the License. You may obtain
 a copy of the License at
     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 License for the specific language governing permissions and limitations
 under the License.
