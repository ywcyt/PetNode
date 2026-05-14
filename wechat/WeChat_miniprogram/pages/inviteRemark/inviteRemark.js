Page({
  data: {
    tags: ['女主人', '男主人', '妈妈', '爸爸', '爷爷', '奶奶', '外公', '外婆', '宝贝', '哥哥', '姐姐', '弟弟', '妹妹'],
    activeTag: ''
  },
  goBack() { wx.navigateBack({ delta: 1 }); },
  selectTag(e) {
    this.setData({ activeTag: e.currentTarget.dataset.tag });
  },
  goNext() {
    wx.navigateTo({ url: '/pages/inviteShare/inviteShare' });
  }
})
