# mediawikiextractor

## 简介

mediawikiextractor 是一个用于从 MediaWiki 网站中提取数据的 Python 脚本。  
从mediawiki网站中页面，处理后并保存为json文件。  

## 使用

1.需要安装'regex'、'requests'、'opencc'、'html2text'库

```sh
pip install regex requests opencc html2text
```

2.运行脚本

```sh
python mediawikiextractor.py --config 配置文件路径 --output 输出文件路径
```

例如：

```sh
python mediawikiextractor.py --config config.json --output data.json
```
