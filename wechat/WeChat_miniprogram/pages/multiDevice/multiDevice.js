Page({
  navToWatch() { wx.navigateTo({ url: '/pages/joke/joke?type=watch' }); },

  // 🚨 注意上一行末尾要加个逗号，然后再写下一个函数！
  navToWidget() { wx.navigateTo({ url: '/pages/joke/joke?type=widget' }); },

  // 统一的返回上一页逻辑，现在它乖乖待在 Page 里面了
  goBack() {
    wx.navigateBack({ delta: 1 });
  }
})
