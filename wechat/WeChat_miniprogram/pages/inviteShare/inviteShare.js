Page({
  goBack() { wx.navigateBack({ delta: 1 }); },

  // 监听原生分享按钮的触发
  onShareAppMessage() {
    return {
      title: '邀请您加入 PetNode 家庭组，共同守护毛孩子们！',
      path: '/pages/index/index', // 别人点开分享卡片后进入的页面
      imageUrl: '/images/DefaultAvatar.png' // 分享卡片的配图
    }
  }
})
