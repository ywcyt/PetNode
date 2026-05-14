const API = require('../../utils/api.js');
const app = getApp();

Page({
  data: {
    userInfo: null,
    editing: false,
    editForm: { nickname: '', avatar_url: '' },

    // 家庭组
    familyMembers: [],
    showInviteModal: false,
    showJoinModal: false,
    inviteToken: '',
    joinToken: ''
  },

  onShow() {
    this.loadUserInfo();
    this.loadFamilyMembers();
  },

  async loadUserInfo() {
    try {
      const user = await API.fetchCurrentUser();
      this.setData({
        userInfo: user,
        editForm: { nickname: user.nickname || '', avatar_url: user.avatar_url || '' }
      });
      app.globalData.userInfo = user;
    } catch (err) {
      console.error('加载用户信息失败:', err);
    }
  },

  async loadFamilyMembers() {
    try {
      const res = await API.fetchFamilyMembers();
      this.setData({ familyMembers: res.members || [] });
    } catch (err) {
      // 未加入家庭组时可能返回错误，忽略
      this.setData({ familyMembers: [] });
    }
  },

  // ===== 编辑资料 =====
  toggleEdit() {
    const user = this.data.userInfo;
    this.setData({
      editing: !this.data.editing,
      editForm: { nickname: user.nickname || '', avatar_url: user.avatar_url || '' }
    });
  },

  onEditInput(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ [`editForm.${field}`]: e.detail.value });
  },

  async saveProfile() {
    if (!this.data.editForm.nickname.trim()) {
      wx.showToast({ title: '昵称不能为空', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '保存中...' });
    try {
      const updated = await API.updateProfile({
        nickname: this.data.editForm.nickname.trim(),
        avatar_url: this.data.editForm.avatar_url.trim() || undefined
      });
      this.setData({ userInfo: updated, editing: false });
      app.globalData.userInfo = updated;
      wx.hideLoading();
      wx.showToast({ title: '保存成功', icon: 'success' });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: '保存失败', icon: 'error' });
    }
  },

  // ===== 家庭组管理 =====
  async createFamily() {
    wx.showLoading({ title: '创建中...' });
    try {
      await API.createFamily();
      wx.hideLoading();
      wx.showToast({ title: '家庭组已创建', icon: 'success' });
      this.loadFamilyMembers();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '创建失败', icon: 'error' });
    }
  },

  async generateInvite() {
    wx.showLoading({ title: '生成中...' });
    try {
      const res = await API.inviteFamily(3600);
      wx.hideLoading();
      this.setData({ inviteToken: res.invite_token, showInviteModal: true });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '生成失败', icon: 'error' });
    }
  },

  copyInviteToken() {
    wx.setClipboardData({
      data: this.data.inviteToken,
      success: () => wx.showToast({ title: '已复制邀请码', icon: 'success' })
    });
  },

  closeInviteModal() {
    this.setData({ showInviteModal: false });
  },

  showJoinInput() {
    this.setData({ showJoinModal: true, joinToken: '' });
  },

  onJoinInput(e) {
    this.setData({ joinToken: e.detail.value });
  },

  async joinFamily() {
    if (!this.data.joinToken.trim()) {
      wx.showToast({ title: '请输入邀请码', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '加入中...' });
    try {
      await API.joinFamily(this.data.joinToken.trim());
      wx.hideLoading();
      wx.showToast({ title: '加入成功', icon: 'success' });
      this.setData({ showJoinModal: false });
      this.loadFamilyMembers();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '加入失败', icon: 'error' });
    }
  },

  closeJoinModal() {
    this.setData({ showJoinModal: false });
  },

  async removeMember(e) {
    const userId = e.currentTarget.dataset.userId;
    const isSelf = userId === (this.data.userInfo && this.data.userInfo.user_id);
    wx.showModal({
      title: isSelf ? '退出家庭组' : '移除成员',
      content: isSelf ? '确定要退出家庭组吗？' : '确定要移除该成员吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await API.removeFamilyMember(userId);
            wx.showToast({ title: isSelf ? '已退出' : '已移除', icon: 'success' });
            this.loadFamilyMembers();
          } catch (err) {
            wx.showToast({ title: '操作失败', icon: 'error' });
          }
        }
      }
    });
  },

  // ===== 退出登录 =====
  handleLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          wx.removeStorageSync('access_token');
          app.globalData.token = null;
          app.globalData.userInfo = null;
          wx.reLaunch({ url: '/pages/login/login' });
        }
      }
    });
  }
});
