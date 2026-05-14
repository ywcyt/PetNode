const api = require('../../utils/api.js');

Page({
  data: {
    currentUserId: '',
    members: []
  },

  onLoad() {
    const userId = wx.getStorageSync('user_id') || '';
    this.setData({ currentUserId: userId });
    this.fetchMembers();
  },

  async fetchMembers() {
    try {
      const data = await api.get('/api/v1/family/members');
      const members = (data.members || []).map(m => ({
        id: m.user_id,
        name: m.nickname || `用户${(m.user_id || '').substring(0, 6)}`,
        phone: `ID: ${(m.user_id || '').substring(0, 8)}`,
        avatar: m.avatar_url || '/images/DefaultAvatar.png',
        role: m.role || 'member',
        isMe: m.user_id === this.data.currentUserId
      }));
      this.setData({ members });
    } catch (_) {
      wx.showToast({ title: '家庭成员加载失败', icon: 'none' });
    }
  },

  kickMember(e) {
    const userId = e.currentTarget.dataset.id;
    const name = e.currentTarget.dataset.name;
    const that = this;

    wx.showModal({
      title: '踢出成员',
      content: `确定要将 ${name} 踢出家庭组吗？`,
      confirmColor: '#ff3b30',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await api.delete(`/api/v1/family/members/${userId}`);
          wx.showToast({ title: '已移除', icon: 'success' });
          that.fetchMembers();
        } catch (_) {
          wx.showToast({ title: '操作失败，请重试', icon: 'none' });
        }
      }
    });
  },

  goBack() {
    wx.navigateBack({ delta: 1 });
  }
});
