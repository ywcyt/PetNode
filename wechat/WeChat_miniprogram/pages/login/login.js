const API = require('../../utils/api.js');
const app = getApp();

Page({
  data: {
    isLoading: false
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
        wx.showToast({ title: '登录成功', icon: 'success' });
        setTimeout(() => { wx.switchTab({ url: '/pages/index/index' }); }, 1000);
      } else {
        wx.setStorageSync('wx_identity_token', authRes.wx_identity_token);
        wx.showToast({ title: '请先绑定账号', icon: 'none' });
        // 后续补上绑定页跳转
      }
    } catch (err) {
      console.error(err);
      wx.showToast({ title: '连接后端失败', icon: 'error' });
    } finally {
      this.setData({ isLoading: false });
      wx.hideLoading();
    }
  }
});