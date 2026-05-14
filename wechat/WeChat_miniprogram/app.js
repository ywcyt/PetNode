const API = require('./utils/api.js');

App({
  onLaunch() {
    const token = wx.getStorageSync('access_token');
    if (token) {
      this.globalData.token = token;
      this.loadUserInfo();
    }
  },

  async loadUserInfo() {
    try {
      const user = await API.fetchCurrentUser();
      this.globalData.userInfo = user;
    } catch (err) {
      console.error('加载用户信息失败', err);
    }
  },

  globalData: {
    token: null,
    userInfo: null,
    currentPetId: null,
    currentDeviceId: null
  }
});
