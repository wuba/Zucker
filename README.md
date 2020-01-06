# Zucker:A easier accurater automate way to calculate aar real size in the apk 


[中文文档](README_CN.md)

> As we all know,that when the project was introduced with AAR, it was not accurate to calculate only the aAR file size. Because aar is unzipped during packaging, the resource files are merged and then compressed, the actual apk footprint may be smaller than the current aar file size. Zucker was born to calculate the size of the target AAR at apk.


## Requirements

- Python 3.7+
- Android Dev
- Gradle 2.0+
- *unx/Windows

## Get Start

The first time you use Zucker for AAR size calculations, it is recommended to compile once on the command line.

Compile-time recommended `gradlew` command to ensure the use of the project's 'gradle' configuration
Perform the following command:
```
./gradlew build
```
Put the `zucker.py` script under the `src` directory in this project in the peer directory of Android Project and execute the following command in the terminal:
```
python zucker.py XXX(Android project)
```
The script is executed automatically, obtaining the dependencies in the project and outputing a level-level node, which can select the target node for AAR size calculation.

Finally, after packaging, the AAR size is displayed on the terminal.

> It is recommended to test the project's 'sample project' first, as detailed in the project [README](Sample/README.md)

## Q&A
- todo

## Contribute

See [CONTRIBUTING](CONTRIBUTING.rst)


## Licence


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