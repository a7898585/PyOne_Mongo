#-*- coding=utf-8 -*-
from flask import Flask,render_template,redirect,abort,make_response,jsonify,request,url_for
from flask_sqlalchemy import Pagination
import json
from collections import OrderedDict
import subprocess
import hashlib
import random
from function import *
from redis import Redis
import time
#######flask
app=Flask(__name__)

rd=Redis(host='localhost',port=6379)

################################################################################
###################################功能函数#####################################
################################################################################
def md5(string):
    a=hashlib.md5()
    a.update(string.encode(encoding='utf-8'))
    return a.hexdigest()

def FetchData(path='/',page=1,per_page=50):
    resp=[]
    if path=='/':
        total=items.find({'grandid':0}).count()
        data=items.find({'grandid':0}).limit(per_page).skip((page-1)*per_page)
        for d in data:
            item={}
            item['name']=d['name']
            item['id']=d['id']
            item['lastModtime']=d['lastModtime']
            item['size']=d['size']
            item['type']=d['type']
            resp.append(item)
    else:
        route=path.split('/')
        pid=0
        for idx,r in enumerate(route):
            if pid==0:
                f=items.find_one({'grandid':idx,'name':r})
            else:
                f=items.find_one({'grandid':idx,'name':r,'parent':pid})
            pid=f['id']
        print {'grandid':idx,'name':r,'parent':pid}
        total=items.find({'grandid':idx+1,'parent':pid}).count()
        data=items.find({'grandid':idx+1,'parent':pid}).limit(per_page).skip((page-1)*per_page)
        for d in data:
            item={}
            item['name']=d['name']
            item['id']=d['id']
            item['lastModtime']=d['lastModtime']
            item['size']=d['size']
            item['type']=d['type']
            resp.append(item)
    return resp,total


def _getdownloadurl(id):
    app_url=GetAppUrl()
    token=GetToken()
    headers={'Authorization':'bearer {}'.format(token),'Content-Type':'application/json'}
    url=app_url+'_api/v2.0/me/drive/items/'+id
    r=requests.get(url,headers=headers)
    data=json.loads(r.content)
    if data.get('@content.downloadUrl'):
        return data.get('@content.downloadUrl')
    else:
        return False

def GetDownloadUrl(id):
    if rd.exists('downloadUrl:{}'.format(id)):
        downloadUrl,ftime=rd.get('downloadUrl:{}'.format(id)).split('####')
        if time.time()-int(ftime)>=downloadUrl_timeout:
            print('{} downloadUrl expired!'.format(id))
            downloadUrl=_getdownloadurl(id)
            ftime=int(time.time())
            k='####'.join([downloadUrl,str(ftime)])
            rd.set('downloadUrl:{}'.format(id),k)
        else:
            print('get {}\'s downloadUrl from cache'.format(id))
            downloadUrl=downloadUrl
    else:
        print('first time get downloadUrl from {}'.format(id))
        downloadUrl=_getdownloadurl(id)
        ftime=int(time.time())
        k='####'.join([downloadUrl,str(ftime)])
        rd.set('downloadUrl:{}'.format(id),k)
    return downloadUrl


def GetName(id):
    item=items.find_one({'id':id})
    return item['name']

def CodeType(ext):
    code_type={}
    code_type['html'] = 'html';
    code_type['htm'] = 'html';
    code_type['php'] = 'php';
    code_type['css'] = 'css';
    code_type['go'] = 'golang';
    code_type['java'] = 'java';
    code_type['js'] = 'javascript';
    code_type['json'] = 'json';
    code_type['txt'] = 'Text';
    code_type['sh'] = 'sh';
    code_type['md'] = 'Markdown';
    return code_type.get(ext.lower())

def file_ico(item):
  ext = item['name'].split('.')[-1].lower()
  if ext in ['bmp','jpg','jpeg','png','gif']:
    return "image";

  if ext in ['mp4','mkv','webm','avi','mpg', 'mpeg', 'rm', 'rmvb', 'mov', 'wmv', 'mkv', 'asf']:
    return "ondemand_video";

  if ext in ['ogg','mp3','wav']:
    return "audiotrack";

  return "insert_drive_file";

def _remote_content(fileid):
    downloadUrl=GetDownloadUrl(fileid)
    if downloadUrl:
        r=requests.get(downloadUrl)
        return r.content
    else:
        return False


def has_password(path):
    if items.count()==0:
        return False
    password=False
    if path=='/':
        if items.find_one({'grandid':0,'name':'.password'}):
            password=_remote_content(items.find_one({'grandid':0,'name':'.password'})['id']).strip()
    else:
        route=path.split('/')
        pid=0
        for idx,r in enumerate(route):
            if pid==0:
                f=items.find_one({'grandid':idx,'name':r})
            else:
                f=items.find_one({'grandid':idx,'name':r,'parent':pid})
            pid=f['id']
        data=items.find_one({'grandid':idx,'name':r,'parent':pid})
        if data:
            password=_remote_content(data['id']).strip()
    return password


################################################################################
###################################试图函数#####################################
################################################################################
@app.before_request
def before_request():
    global referrer
    referrer=request.referrer if request.referrer is not None else 'no-referrer'


@app.route('/<path:path>',methods=['POST','GET'])
@app.route('/',methods=['POST','GET'])
def index(path='/'):
    code=request.args.get('code')
    page=request.args.get('page',1,type=int)
    password=has_password(path)
    md5_p=md5(path)
    if request.method=="POST":
        password1=request.form.get('password')
        if password1==password:
            resp=make_response(redirect(url_for('.index',path=path)))
            resp.delete_cookie(md5_p)
            resp.set_cookie(md5_p,password)
            return resp
    if password!=False:
        if not request.cookies.get(md5_p) or request.cookies.get(md5_p)!=password:
            return render_template('password.html',path=path)
    if code is not None:
        Atoken=OAuth(code)
        if Atoken.get('access_token'):
            with open('data/Atoken.json','w') as f:
                json.dump(Atoken,f,ensure_ascii=False)
            app_url=GetAppUrl()
            refresh_token=Atoken.get('refresh_token')
            with open('data/AppUrl','w') as f:
                f.write(app_url)
            token=ReFreshToken(refresh_token)
            with open('data/token.json','w') as f:
                json.dump(token,f,ensure_ascii=False)
            return make_response('<h1>授权成功!<a href="/">点击进入首页</a></h1>')
        else:
            return jsonify(Atoken)
    else:
        if items.count()==0:
            if not os.path.exists('data/token.json'):
                return make_response('<h1><a href="{}">点击授权账号</a></h1>'.format(LoginUrl))
            else:
                subprocess.Popen('python function.py UpdateFile',shell=True)
                return make_response('<h1>正在更新数据!</h1>')
        resp,total = FetchData(path,page)
        pagination=Pagination(query=None,page=page, per_page=50, total=total, items=None)
        return render_template('index.html',pagination=pagination,items=resp,path=path,endpoint='.index')


@app.route('/file/<fileid>',methods=['GET','POST'])
def show(fileid):
    downloadUrl=GetDownloadUrl(fileid)
    if request.method=='POST':
        name=GetName(fileid)
        ext=name.split('.')[-1]
        url=request.url.replace(':80','').replace(':443','')
        if ext in ['csv','doc','docx','odp','ods','odt','pot','potm','potx','pps','ppsx','ppsxm','ppt','pptm','pptx','rtf','xls','xlsx']:
            url = 'https://view.officeapps.live.com/op/view.aspx?src='+urllib.quote(downloadUrl)
            return redirect(url)
        elif ext in ['bmp','jpg','jpeg','png','gif']:
            return render_template('show/image.html',downloadUrl=downloadUrl,url=url)
        elif ext in ['mp4','webm']:
            return render_template('show/video.html',downloadUrl=downloadUrl,url=url)
        elif ext in ['mp4','webm','avi','mpg', 'mpeg', 'rm', 'rmvb', 'mov', 'wmv', 'mkv', 'asf']:
            downloadUrl=downloadUrl.replace('thumbnail','videomanifest')+'&part=index&format=dash&useScf=True&pretranscode=0&transcodeahead=0'
            return render_template('show/video2.html',downloadUrl=downloadUrl,url=url)
        elif ext in ['ogg','mp3','wav']:
            return render_template('show/audio.html',downloadUrl=downloadUrl,url=url)
        elif CodeType(ext) is not None:
            content=requests.get(downloadUrl).content
            return render_template('show/code.html',content=content,url=url,language=CodeType(ext))
        else:
            content=requests.get(downloadUrl).content
            return render_template('show/any.html',content=content)
    else:
        if sum([i in referrer for i in allow_site])>0:
            return redirect(downloadUrl)
        else:
            return abort(404)



app.jinja_env.globals['FetchData']=FetchData
app.jinja_env.globals['file_ico']=file_ico
app.jinja_env.globals['title']='pyone'
################################################################################
#####################################启动#######################################
################################################################################
if __name__=='__main__':
    app.run(port=58693,debug=True)



