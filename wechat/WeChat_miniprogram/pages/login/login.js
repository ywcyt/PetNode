const api = require('../../utils/api.js');

Page({
  data: {
    isAgreed: false,
    showToast: false,
    toastMsg: '',
    // 绑定状态：'idle' | 'binding'
    bindStatus: 'idle',
  },

  toggleAgree() {
    this.setData({ isAgreed: !this.data.isAgreed });
  },

  showCustomToast(msg) {
    this.setData({ toastMsg: msg, showToast: true });
    setTimeout(() => {
      this.setData({ showToast: false });
    }, 3000);
  },

  /**
   * 一键登录（完整流程）
   *  1. wx.login() 获取 code
   *  2. POST /api/v1/wechat/auth  →  已绑定直接拿 token，未绑定拿 wx_identity_token
   *  3. 未绑定时自动调用 POST /api/v1/wechat/bind 创建用户 + 绑定
   */
  async handleWechatLogin() {
    console.log('[login] 点击登录按钮, isAgreed=', this.data.isAgreed);

    if (!this.data.isAgreed) {
      this.showCustomToast('请先阅读并勾选底部用户协议');
      return;
    }

    wx.showLoading({ title: '登录中...', mask: true });
    console.log('[login] 开始 wx.login()...');

    try {
      // Step 1: wx.login()
      const loginRes = await new Promise((resolve, reject) => {
        wx.login({ success: resolve, fail: reject });
      });
      console.log('[login] wx.login() 成功, code=', loginRes.code);

      if (!loginRes.code) {
        wx.hideLoading();
        this.showCustomToast('微信登录调用失败');
        return;
      }

      // Step 2: /wechat/auth
      console.log('[login] 调用 /api/v1/wechat/auth...');
      const authData = await api.post('/api/v1/wechat/auth', { code: loginRes.code });
      console.log('[login] /wechat/auth 返回:', JSON.stringify(authData));
      wx.hideLoading();

      if (authData.access_token) {
        // 已绑定 → 直接登录
        wx.setStorageSync('access_token', authData.access_token);
        if (authData.user_id) {
          wx.setStorageSync('user_id', authData.user_id);
        }
        this.showCustomToast('登录成功');
        setTimeout(() => {
          wx.navigateBack({ delta: 1, fail: () => wx.redirectTo({ url: '/pages/index/index' }) });
        }, 1000);
        return;
      }

      // 未绑定 → 自动调用 /bind 创建新用户
      if (!authData.is_bound && authData.wx_identity_token) {
        this.setData({ bindStatus: 'binding' });
        wx.showLoading({ title: '注册中...', mask: true });

        const bindData = await api.post('/api/v1/wechat/bind', {
          wx_identity_token: authData.wx_identity_token,
        });
        wx.hideLoading();

        if (bindData.access_token) {
          wx.setStorageSync('access_token', bindData.access_token);
          if (bindData.user_id) {
            wx.setStorageSync('user_id', bindData.user_id);
          }
          this.showCustomToast('注册并登录成功');
          setTimeout(() => {
            wx.navigateBack({ delta: 1, fail: () => wx.redirectTo({ url: '/pages/index/index' }) });
          }, 1000);
        } else {
          wx.showModal({
            title: '注册失败',
            content: '服务器未返回 token，请重试',
            showCancel: false,
          });
        }
        this.setData({ bindStatus: 'idle' });
      }
    } catch (error) {
      console.error('[login] 登录失败:', error);
      wx.hideLoading();
      this.setData({ bindStatus: 'idle' });
      wx.showModal({
        title: '登录失败',
        content: error.message || '服务器连接异常，请重试',
        showCancel: false,
      });
    }
  },

  goToProtocol() {
    console.log('跳转服务协议');
  },
  goToPrivacy() {
    console.log('跳转隐私政策');
  }
});
