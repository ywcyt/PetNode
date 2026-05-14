App({
  onLaunch() {
    const token = wx.getStorageSync('access_token');
    if (token) {
      this.globalData.token = token;
    }
    const autoTheme = wx.getStorageSync('auto_theme');
    if (autoTheme !== '') {
      this.globalData.autoTheme = autoTheme;
    }
  },

  onShow(options) {
    // 每次从后台切回前台时，如果没有 token 则跳转登录页
    const token = wx.getStorageSync('access_token');
    if (!token) {
      this.globalData.token = null;
    }
  },

  checkLogin() {
    const token = wx.getStorageSync('access_token');
    return !!token;
  },

  globalData: {
    token: null,
    userInfo: null,
    currentPetId: null,
    currentDeviceId: null,
    autoTheme: true
  }
})
