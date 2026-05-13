App({
  onLaunch() {
    const token = wx.getStorageSync('access_token');
    if (token) {
      this.globalData.token = token;
    }
  },
  globalData: {
    token: null,
    userInfo: null,
    currentPetId: null,
    currentDeviceId: null
  }
})