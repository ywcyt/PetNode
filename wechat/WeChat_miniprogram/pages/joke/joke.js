Page({
  data: { text: '' },
  onLoad(options) {
    let text = '你不会真的以为这里有什么吧(ﾉ≧∀≦)ﾉ・‥…━━━★'; // 默认

    // 根据参数动态替换文本
    if (options.type === 'flower') {
      text = '你不会真的以为这里有什么吧(◕‿◕✿)';
    } else if (options.type === 'watch') {
      text = '这个页面旨在后续和您的Apple Watch、华为手表、小米手表等一系列手表联动控制。';
    } else if (options.type === 'widget') {
      text = '这个功能旨在后续在您的手机上添加实时监控的小组件。';
    }
    this.setData({ text });
  },

  // 🚨 新增的返回函数
  goBack() {
    wx.navigateBack({ delta: 1 });
  }
})
