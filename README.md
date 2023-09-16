# mediawikiextractor

## 简介

mediawikiextractor 是一个用于从 MediaWiki 网站中提取数据的 Python 脚本。
从mediawiki网站中获取cirrusdoc，处理后并保存为json文件。
目前仅适用于萌娘百科，其他 MediaWiki 网站需要修改部分表达式。

## 使用

1. 需要安装'regex'、'requests'库

    ```sh
    pip install regex requests
    ```

2. 运行脚本

    ```sh
    python mediawikiextractor.py --config 配置文件路径 --output 输出文件路径
    ```

    例如：

    ```sh
    python mediawikiextractor.py --config config.json --output data.json
    ```
