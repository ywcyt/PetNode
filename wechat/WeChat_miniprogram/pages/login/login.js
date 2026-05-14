const API = require('../../utils/api.js');
const app = getApp();

Page({
  data: {
    isLoading: false,
    isNewUser: false,
    wxIdentityToken: ''
  },

  async handleWechatLogin() {
    if (this.data.isLoading) return;
    this.setData({ isLoading: true });
    wx.showLoading({ title: '登录中...' });

    try {
      const { code } = await wx.login();
      if (!code) throw new Error('凭证获取失败');

      const authRes = await API.wxLoginAndAuth(code);

      if (authRes.is_bound) {
        wx.setStorageSync('access_token', authRes.access_token);
        app.globalData.token = authRes.access_token;
        await app.loadUserInfo();
        wx.showToast({ title: '登录成功', icon: 'success' });
        setTimeout(() => { wx.switchTab({ url: '/pages/index/index' }); }, 800);
      } else {
        wx.setStorageSync('access_token', authRes.wx_identity_token);
        app.globalData.token = authRes.wx_identity_token;
        this.autoBindNewUser();
      }
    } catch (err) {
      console.error('登录失败:', err);
      wx.showToast({ title: '连接服务器失败', icon: 'error' });
    } finally {
      this.setData({ isLoading: false });
      wx.hideLoading();
    }
  },

  async autoBindNewUser() {
    try {
      wx.showLoading({ title: '正在注册...' });
      const bindRes = await API.bindWechatUser({ nickname: '微信用户' });
      wx.setStorageSync('access_token', bindRes.access_token);
      app.globalData.token = bindRes.access_token;
      await app.loadUserInfo();
      wx.hideLoading();
      wx.showToast({ title: '注册成功', icon: 'success' });
      setTimeout(() => { wx.switchTab({ url: '/pages/index/index' }); }, 800);
    } catch (err) {
      wx.hideLoading();
      console.error('自动注册失败:', err);
      wx.showToast({ title: '注册失败，请重试', icon: 'error' });
    }
  }
});
