const app = getApp();

Page({
  data: {
    isDark: true,
    tempArray: ['摄氏度 ℃', '华氏度 ℉'],
    tempIndex: 0
  },
  onLoad() {
    this.setData({ isDark: app.globalData.autoTheme });
  },
  onTempChange(e) {
    this.setData({ tempIndex: e.detail.value });
  },
  onDarkChange(e) {
    const val = e.detail.value;
    this.setData({ isDark: val });
    app.globalData.autoTheme = val;
    wx.setStorageSync('auto_theme', val);
  },
  navToJoke() {
    wx.navigateTo({ url: '/pages/joke/joke?type=flower' });
  },
  navToFamily() {
    wx.navigateTo({ url: '/pages/familyManage/familyManage' });
  },

  handleLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (!res.confirm) return;
        wx.removeStorageSync('access_token');
        wx.removeStorageSync('user_id');
        app.globalData.token = null;
        wx.navigateBack({ delta: 1, fail: () => wx.redirectTo({ url: '/pages/index/index' }) });
      }
    });
  },

  goBack() {
    wx.navigateBack({ delta: 1 });
  }
})
