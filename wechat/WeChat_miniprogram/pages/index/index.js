Page({
  data: {
    currentTab: 0, 
    devices: [
      { id: 1, name: '狗子1号', status: '在线 - 睡觉中', avatar: '🐕' }, 
      { id: 2, name: '狗子2号', status: '在线 - 玩耍中', avatar: '🐕' },
      { id: 3, name: '狗子3号', status: '离线', avatar: '🐕' },
      { id: 4, name: '狗子4号', status: '电量低', avatar: '🐕' }
    ],
    // 新增：用于控制白天/黑夜主题的开关
    isDaytime: true 
  },

  /**
   * 页面加载时，检查当前时间
   */
  onLoad() {
    this.checkTime();
  },

  /**
   * 每次回到首页时，都重新检查一次时间（防止跨天/跨夜）
   */
  onShow() {
    this.checkTime();
  },

  /**
   * 判断白天黑夜的逻辑
   */
  checkTime() {
    const hour = new Date().getHours();
    // 逻辑：大于等于 6点，且小于 18点，算作白天
    const isDaytime = hour >= 6 && hour < 18;
   //const isDaytime = false;
    this.setData({ isDaytime });
  },

  /**
   * 原有的滑动与点击跳转逻辑
   */
  onSwiperChange(e) {
    this.setData({ currentTab: e.detail.current });
  },
  switchTab(e) {
    const index = e.currentTarget.dataset.index;
    this.setData({ currentTab: index });
  },
  goToDetail(e) {
    const petId = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/petDetail/petDetail?id=${petId}` });
  },

  /**
   * 🚨 新增：调用微信原生扫码功能
   */
  scanDevice() {
    wx.scanCode({
      success: (res) => {
        // 扫码成功后，res.result 就是二维码里的内容
        console.log('扫码结果:', res.result);
        wx.showToast({ title: '扫码成功', icon: 'success' });
        // 后续我们可以在这里把扫到的设备 ID 发给后端进行绑定
      },
      fail: (err) => {
        // 如果用户自己点了左上角退出相机，不报错；如果是真扫码失败才提示
        if (err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '扫码失败', icon: 'error' });
        }
      }
    });
  }
})