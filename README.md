# mediawikiextractor

## 介绍

mediawikiextractor 是一个用于从 MediaWiki 网站中爬取数据的 Python 脚本。  

与从百科数据库备份转储中提取不同，mediawikiextractor不需要处理模板，能获取更干净完整的文本  
不过这也意味着其一次能爬取的页面数量有限，且速度与你的网速有关

mediawikiextractor支持在原有的数据上继续爬取与更新数据(需要`output_format`为列表)  
每次运行mediawikiextractor对于没有变化的页面都会重新清理文本  
如果你删除了部分`cleaning_rule`可能导致你获取的数据与预期不符

## 使用

1.需要安装'regex'、'requests'、'html2text'、'markdown'、'bs4'库

```sh
pip install -r requirements.txt
```

2.运行脚本

```sh
python mediawikiextractor.py --config 配置文件路径 --output 输出文件路径
```

例如：

```sh
python mediawikiextractor.py --config config.json --output data.json
```

## 配置

配置文件为json格式，以下是一个例子：

```json
{
        "name": "萌娘百科",
        "source": "moegril",
        "site_url": "https://zh.moegirl.org.cn/index.php",
        "api": "https://zh.moegirl.org/api.php",
        "output_format": ["plain","markdown"],
        "page_ids": [19765,275042,104819,205103,215911,291578,414748,546166,322316,343884,286448,385770,33291,8639,556824,297456,20490,31450,33234,35578,153449,33227,255209,574022,374048,28845,308168],
        "categories": ["恋爱冒险游戏", "视觉小说","Galgame公司","宅文化术语","萌宅用语","Little_Busters!","AIR","Angel_Beats","CLANNAD","Charlotte","Harmonia(Key)#","Kanon","LOOPERS","MOON.","LUNARiA_-Virtualized_Moonchild-","ONE～辉之季节～","Rewrite","Summer_Pockets","星之梦","星之终途","ATRI","爱上火车","初音岛","9-nine-","常轨脱离Creative","住在拔作岛上的贫乳应该如何是好？","苍之彼方的四重奏","美少女万华镜","缘之空","灰色系列","少女领域","千恋万花","FORTUNE ARTERIAL","柚子社作品","Palette作品","Smile作品","Recette作品","BUG SYSTEM作品","SWEET&TEA作品","猫猫社作品","YAMAYURI GAMES作品","Navel作品","Navel honeybell作品","AUGUST作品","Whirlpool作品","戏画作品"],
        "exclude_ids": [561570,280950,28533],
        "exclude_categories": ["网页游戏"],
        "exclude_titles": ["Category:.*","Template:.*","User:.*"],
        "cleaning_rule": [".*萌娘百科祝您在本站度过愉快的时光。(?: |\n)*(?!.*萌娘百科祝您在本站度过愉快的时光)",".*祝您在萌娘百科度过愉快的时光。(?: |\n)*(?!.* 祝您在萌娘百科度过愉快的时光)",".*本条目经赤座茜审阅，可以给全世界的妹控观赏，阅读前请大声欢呼三声有个能干的妹妹真好！(?: |\n)*(?!.*本条目经赤座茜审阅，可以给全世界的妹控观赏，阅读前请大声欢呼三声有个能干的妹妹真好！)",".*穹妹的凝望本条目经过穹妹的认可，可以给全世界的妹控观赏。 观看本文前请大声欢呼三声有个能干的妹妹真好，否则属于思想犯罪，下场可能是：  被推到叉依姬神社的湖里淹死或者转学； 与春日野悠搞姬，从此过上性福快乐的生活 被自己的妹妹抛弃(?: |\n)*(?!.*穹妹的凝望本条目经过穹妹的认可，可以给全世界的妹控观赏。 观看本文前请大声欢呼三声有个能干的妹妹真好，否则属于思想犯罪，下场可能是：  被推到叉依姬神社的湖里淹死或者转学； 与春日野悠搞姬，从此过上性福快乐的生活 被自己的妹妹抛弃)",".*编辑前请阅读  Wiki入门  或  萌娘百科:编辑规范  ，并查找相关资料哦。(?: |\n)*(?!.*编辑前请阅读  Wiki入门  或  萌娘百科:编辑规范  ，并查找相关资料哦。)",".*今天（[1-9]{1,2}月[1-9]{1,2}日）是这位萌娘的生日，让我们一起祝她生日快乐！(?: |\n)*(?!.*今天（[1-9]{1,2}月[1-9]{1,2}日）是这位萌娘的生日，让我们一起祝她生日快乐！)","(?:\\n)+#* *外部链接(?:[与及和]注释)*(?:\\n)+.*","(?:\\n)+#* *注释(?:[与及和]*外部链接)* *(?:\\n)+.*",".*具体使用方法详见  模板说明文档 *。* *(?:\\n)*"]
}
```

更多例子见[VisualNovel-Dataset](https://github.com/chenmozhijin/VisualNovel-Dataset/tree/main/.github/workflows/config)

### 配置说明

| 名称                            | 介绍
|---------------------------------|---------------------------------------------------
| `name`                          | 网站名称，脚本不会读取。
| `source`                        | 数据来源，输出文件中的每个页面字典中都将包含此元素。
| `site_url`                      | 网站的index.php地址，如：`https://ja.wikipedia.org/w/index.php`。用于获取获取页面内容。
| `api`                           | 网站的api地址，如：`https://ja.wikipedia.org/w/api.php`。用于获取获取页面基本信息。
| `output_format`                 | 输出文本格式，目前支持：`plain`(纯文本)、`markdown`(不包含任何链接)、`markdown with links`(包含链接包括图片链接)。值可以为字符串或列表。
| `page_ids`                      | 需要爬取的页面id列表。
| `categories`                    | 需要爬取的分类列表。
| `exclude_ids`                   | 需要排除的页面id列表。
| `exclude_categories`            | 需要排除的分类列表。
| `exclude_titles`                | 需要排除的页面标题列表，可以为正表达式。
| `cleaning_rule`                 | 清理规则，为列表其中每个元素为正表达式，匹配到的内容将会在文本中删除。

### 注意

1. 如果你修改了`cleaning_rule`建议输出到一个新的文件，而不是增量更新。
2. 正表达式需要符合json格式，如`#* *脚注  \[  編集  \].*`需要修改为`#* *脚注  \\[  編集  \\].*`。
3. 如果你希望排除指定的页面建议使用`exclude_ids`，因为`exclude_titles`需要用api获取页面信息后再排除，会增加请求量。
4. 在处理非`markdown with links`格式时，图片的说明文字将被删除。
5. `output_format`为字符串时无法增量更新。

## 输出

输出文件为json格式，类似以下格式：

```json
[
    {
        "title": "能美库特莉亚芙卡",
        "pageid": 13078,
        "version": 6735922,
        "timestamp": "2023-03-14T11:39:15Z",
        "source": "moegril",
        "text": {
            "plain": "纯文本格式的页面数据",
            "markdown": "markdown格式的页面数据"
        }
    },
    {
        "title": "Kud Wafter",
        "pageid": 39569,
        "version": 7073610,
        "timestamp": "2023-09-27T09:44:07Z",
        "source": "moegril",
        "text": {
            "plain": "纯文本格式的页面数据",
             "markdown": "markdown格式的页面数据",
        }
    }
]
```

其中如果你的`output_format`为字符串类型则输出的`text`字段也为字符串，如果为列表类型为则输出的`text`字段字典。
