import scrapy
import re
from bs4 import BeautifulSoup


class PttcrawlerHwSpider(scrapy.Spider):
    custom_settings = {
        'LOG_LEVEL': 'DEBUG',       # Log等级，默认是最低级别debug
        'ROBOTSTXT_OBEY': False,    # default Obey robots.txt rules
        'DOWNLOAD_DELAY': 2,        # 下载延时，默认是0
        'COOKIES_ENABLED': True,    # 默认enable，爬取登录后的数据时需要启用。 会增加流量，因为request和response中会多携带cookie的部分
        'COOKIES_DEBUG': True,      # 默认值为False,如果启用，Scrapy将记录所有在request(Cookie 请求头)发送的cookies及response接收到的cookies(Set-Cookie 接收头)。
        'DOWNLOAD_TIMEOUT': 25,     # 下载超时，既可以是爬虫全局统一控制，也可以在具体请求中填入到Request.meta中，Request.meta['download_timeout']
    }
    
    name = 'PTTCrawler_HW'
    allowed_domains = ['ptt.cc']
    start_urls = ['https://www.ptt.cc/bbs/BuyTogether/M.1602602834.A.B60.html']
    cookies = {'over18': '1'}

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url=url, cookies=self.cookies, callback=self.parse, 
                                 meta = {'dont_redirect': True, 'handle_httpstatus_list': [302]}, 
                                 dont_filter=True)
            
    def parse(self, response):
        # 假設網頁回應不是 200 OK 的話, 我們視為傳送請求失敗
        if response.status != 200:
            print('Error - {} is not available to access'.format(response.url))
            return
        
        # 將網頁回應的 HTML 傳入 BeautifulSoup 解析器, 方便我們根據標籤 (tag) 資訊去過濾尋找
        soup = BeautifulSoup(response.text,'lxml')
        
        # BeautifulSoup 注意
        # select的 寫法和 find 有區別，select是標簽和 class 都在一個字符串裏， find 是兩個字符串，用逗號隔開
        # find 只取第一個值，返回的是字符串
        # find——all 是全部的值和 select 一樣，是一個列表; find-all 加 limit=1 屬性後只返回第一個
        
        # 取得文章內容主體
        main_content = soup.find(id='main-content')
        

        # 假如文章有屬性資料 (meta), 我們在從屬性的區塊中爬出作者 (author), 文章標題 (title), 發文日期 (date)
        metas = main_content.select('div.article-metaline')
        author = ''
        title = ''
        date = ''
        if metas:
            if metas[0].select('span.article-meta-value')[0]:
                author = metas[0].select('span.article-meta-value')[0].string
            if metas[1].select('span.article-meta-value')[0]:
                title = metas[1].select('span.article-meta-value')[0].string
            if metas[2].select('span.article-meta-value')[0]:
                date = metas[2].select('span.article-meta-value')[0].string

        # 從 main_content 中移除 meta 資訊（author, title, date 與其他看板資訊）
        for m in main_content:
            m.extract()
        
        for m in main_content.select('div.article-metaline-right'):
            m.extract()
        

        # 取得留言區主體 
        pushes = main_content.find_all('div', class_='push')
        for p in pushes:
            p.extract()
         
        # 取得發文 IP 位址
        # 因為字串中包含特殊符號跟中文, 這邊建議使用 unicode 的型式 u'...'
        try:
            ip = main_content.find(text=re.compile(u'※ 發信站:'))
            ip = re.search('[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*', ip).group()
        except Exception as e:
            ip = ''
            
        # 移除文章主體中 '※ 發信站:', '◆ From:', 空行及多餘空白 (※ = u'\u203b', ◆ = u'\u25c6')
        # 保留英數字, 中文及中文標點, 網址, 部分特殊符號
        # stripped_strings ==> https://blog.csdn.net/qq_22592457/article/details/100597190
        filtered = []
        for v in main_content.stripped_strings:
            # 假如字串開頭不是特殊符號或是以 '--' 開頭的, 我們都保留其文字
            if v[0] not in [u'※', u'◆'] and v[:2] not in [u'--']:
                filtered.append(v)
                
        # 定義一些特殊符號與全形符號的過濾器
        expr = re.compile(u'[^一-龥。；，：“”（）、？《》\s\w:/-_.?~%()]')
        for i in range(len(filtered)):
            filtered[i] = re.sub(expr, '', filtered[i])
            
        # 移除空白字串, 組合過濾後的文字即為文章本文 (content)
        filtered = [i for i in filtered if i]
        content = ' '.join(filtered)

        # 處理留言區
        # p 計算推文數量
        # b 計算噓文數量
        # n 計算箭頭數量
        p, b, n = 0, 0, 0
        messages = []
        for push in pushes:
            # 假如留言段落沒有 push-tag 就跳過
            if not push.find('span', 'push-tag'):
                continue
            
            # 過濾額外空白與換行符號
            # push_tag 判斷是推文, 箭頭還是噓文
            # push_userid 判斷留言的人是誰
            # push_content 判斷留言內容
            # push_ipdatetime 判斷留言日期時間
            push_tag = push.find('span', 'push-tag').string.strip(' \t\n\r')
            push_userid = push.find('span', 'push-userid').string.strip(' \t\n\r')
            push_content = push.find('span', 'push-content').strings
            push_content = ' '.join(push_content)[1:].strip(' \t\n\r')
            push_ipdatetime = push.find('span', 'push-ipdatetime').string.strip(' \t\n\r')

            # 整理打包留言的資訊, 並統計推噓文數量
            messages.append({
                'push_tag': push_tag,
                'push_userid': push_userid,
                'push_content': push_content,
                'push_ipdatetime': push_ipdatetime})
            if push_tag == u'推':
                p += 1
            elif push_tag == u'噓':
                b += 1
            else:
                n += 1
        
        # 統計推噓文
        # count 為推噓文相抵看這篇文章推文還是噓文比較多
        # all 為總共留言數量 
        message_count = {'all': p+b+n, 'count': p-b, 'push': p, 'boo': b, 'neutral': n}
        
        # 整理文章資訊
        data = {
            'url': response.url,
            'article_author': author,
            'article_title': title,
            'article_date': date,
            'article_content': content,
            'ip': ip,
            'message_count': message_count,
            'messages': messages
        }
        yield data