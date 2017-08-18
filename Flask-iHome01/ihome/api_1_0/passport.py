# -*- coding:utf-8 -*-

import re

from flask import jsonify, request, current_app, session
from ihome.models import User
from ihome.utils.response_code import RET
from ihome import db, redis_store
from ihome.utils.commons import login_required
from . import api


@api.route("/users", methods=["POST"])
def register():

    user_data = request.get_json()
    if not user_data:
        return jsonify(errno=RET.PARAMERR, errmsg="参数不完整")

    mobile = user_data.get("mobile")  
    sms_code = user_data.get("sms_code")  
    password = user_data.get("password")  

    
    if not all([mobile, sms_code, password]):
        return jsonify(errno=RET.PARAMERR, errmsg="参数不完整")


    if not re.match(r"1[34578]\d{9}$", mobile):
        return jsonify(errno=RET.PARAMERR, errmsg="手机号格式不正确")

    try:
        real_sms_code = redis_store.get("SMSCode_" + mobile)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="读取验证码异常")


    if not real_sms_code:
        return jsonify(errno=RET.DATAERR, errmsg="短信验证码过期")


    if real_sms_code != str(sms_code):
        return jsonify(errno=RET.DATAERR, errmsg="短信验证码无效")


    try:
        redis_store.delete("SMSCode_" + mobile)
    except Exception as e:
        current_app.logger.error(e)


    user = User(name=mobile, mobile=mobile)

    user.password = password
    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DATAEXIST, errmsg="手机号已存在")


    session["user_id"] = user.id
    session["name"] = mobile
    session["mobile"] = mobile

    return jsonify(errno=RET.OK, errmsg="OK", data=user.to_dict())

