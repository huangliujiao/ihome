# -*- coding:utf-8 -*-

import re
import random
#jsonify用来返回前端json数据
from flask import request, jsonify, current_app, make_response
from ihome.utils.response_code import RET
from ihome.utils.captcha.captcha import captcha
from ihome.utils import sms
from ihome import redis_store, constants
from ihome.models import User
from . import api

#生成图片验证码
@api.route("/imagecode/<image_code_id>", methods=["GET"])
def generate_image_code(image_code_id):
    #调用第三方接口来实现图片验证码的生成，验证码的名字，验证码的内容，验证码图片
    name, text, image = captcha.generate_captcha()
    #操作数据库，要使用异常处理，主要为了防止数据库操作出现意外，比如网络原因。
    try:
        #把获取的图片验证码存储到redis数据库中
        redis_store.setex("ImageCode_" + image_code_id, constants.IMAGE_CODE_REDIS_EXPIRES, text)
    except Exception as e:
        current_app.logger.error(e)
        #返回前端页面错误信息
        return jsonify(errno=RET.DBERR, errmsg="保存图片验证码失败")
    else:
        #没有异常信息的情况下，生成验证码，返回前端
        response = make_response(image)     
        response.headers["Content-Type"] = "image/jpg"
        return response

#短信验证码
@api.route("/smscode/<mobile>", methods=["GET"])
def send_sms_code(mobile):
    """
    1、首先验证参数是否存在
    2、其次验证手机号格式
    3、验证图片验证码
    4、验证手机号是否存在
    5、生成并发送短信验证码

     """
    #获取参数
    image_code = request.args.get("text") 
    image_code_id = request.args.get("id") 
    #首先验证参数是否存在
    if not all([mobile, image_code, image_code_id]):
        return jsonify(errno=RET.PARAMERR, errmsg="参数错误")
    #验证手机号格式，如果错误返回前端错误信息
    if not re.match(r"^1[34578]\d{9}$", mobile):
        return jsonify(errno=RET.PARAMERR, errmsg="手机号格式错误")
    try:
        #获取redis数据库中存储的真实图片验证码  
        real_image_code = redis_store.get("ImageCode_" + image_code_id)
    except Exception as e:
        current_app.logger.error(e)
        #获取失败，返回前端错误信息
        return jsonify(errno=RET.DBERR, errmsg="查询数据异常") 
    #图片验证码只可以验证一次，如果错误直接返回错误信息
    if not real_image_code:
        return jsonify(errno=RET.DATAERR, errmsg="图片验证码过期")    
    try:
        #如果图片验证码过期，删除数据库中的缓存验证码
        redis_store.delete("ImageCode_" + image_code_id)
    except Exception as e:
        current_app.logger.error(e)    
    #比较验证码，统一把验证码转换成小写，如果不同直接返回错误信息
    if image_code.lower() != real_image_code.lower():
        return jsonify(errno=RET.DATAERR, errmsg="图片验证码错误")    
    try:
        #手机号符合要求后，需要确认用户是否已注册，
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
    else:
        if user is not None:
            return jsonify(errno=RET.DBERR, errmsg="手机号已存在")   
    #生成短信验证码 
    sms_code = '%06d' % random.randint(0, 1000000)    
    try:
        #把短信验证码缓存到redis数据库中，
        redis_store.setex("SMSCode_" + mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="保存数据出现错误")    
    try:
        #调用了第三方接口，实现短信发送
        ccp = sms.CCP()
        result = ccp.send_template_sms(mobile, [sms_code, constants.SMS_CODE_REDIS_EXPIRES/60], 1)
    except Exception as e:
        current_app.logger.error(e)
        #发送短信失败需要给前端发送错误信息
        return jsonify(errno=RET.THIRDERR, errmsg="发送短信异常")
    #错误信息判断的语法格式，建议把常量信息放在等号前面
    if 0 == result:
        return jsonify(errno=RET.OK, errmsg="发送成功")
    else:
        return jsonify(errno=RET.THIRDERR, errmsg="发送短信失败")
