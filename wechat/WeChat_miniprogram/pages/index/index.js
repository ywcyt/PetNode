const API = require('../../utils/api.js');
const app = getApp();

Page({
  data: {
    currentTab: 0,
    devices: [],
    isDaytime: true,
    loading: false,

    // 绑定设备弹窗
    showBindModal: false,
    scannedDeviceId: '',
    bindForm: { pet_name: '', breed: '', weight: '' },

    // 我的页面
    userInfo: null
  },

  onLoad() {
    this.checkTime();
    this.loadPets();
  },

  onShow() {
    this.checkTime();
    this.loadPets();
    this.loadUserInfo();
  },

  onPullDownRefresh() {
    Promise.all([this.loadPets(), this.loadUserInfo()]).then(() => {
      wx.stopPullDownRefresh();
    });
  },

  checkTime() {
    const hour = new Date().getHours();
    const isDaytime = hour >= 6 && hour < 18;
    this.setData({ isDaytime });
  },

  async loadPets() {
    if (this.data.loading) return;
    this.setData({ loading: true });
    try {
      const res = await API.fetchPets();
      const devices = (res.pets || []).map(pet => ({
        id: pet.pet_id,
        name: pet.pet_name || '未命名',
        status: pet.breed || '查看详情',
        avatar: pet.avatar_url || '🐕',
        device_id: pet.device_id
      }));
      this.setData({ devices });
    } catch (err) {
      console.error('加载宠物列表失败:', err);
      if (err !== 'Unauthorized') {
        wx.showToast({ title: '加载失败', icon: 'none' });
      }
    } finally {
      this.setData({ loading: false });
    }
  },

  async loadUserInfo() {
    try {
      const user = await API.fetchCurrentUser();
      this.setData({ userInfo: user });
      app.globalData.userInfo = user;
    } catch (err) {
      // 未登录或 token 失效时忽略
    }
  },

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

  // ===== 扫码绑定设备 =====
  scanDevice() {
    wx.scanCode({
      success: (res) => {
        const deviceId = res.result.trim();
        this.setData({
          showBindModal: true,
          scannedDeviceId: deviceId,
          bindForm: { pet_name: '', breed: '', weight: '' }
        });
      },
      fail: (err) => {
        if (err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '扫码失败', icon: 'error' });
        }
      }
    });
  },

  onBindInput(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ [`bindForm.${field}`]: e.detail.value });
  },

  closeBindModal() {
    this.setData({ showBindModal: false });
  },

  async submitBind() {
    const { pet_name, breed, weight } = this.data.bindForm;
    if (!pet_name.trim()) {
      wx.showToast({ title: '请输入宠物名称', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '绑定中...' });
    try {
      await API.bindDevice({
        device_id: this.data.scannedDeviceId,
        pet_name: pet_name.trim(),
        breed: breed.trim() || undefined,
        weight: weight ? parseFloat(weight) : undefined
      });
      wx.hideLoading();
      wx.showToast({ title: '绑定成功', icon: 'success' });
      this.setData({ showBindModal: false });
      this.loadPets();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '绑定失败', icon: 'error' });
    }
  },

  // ===== 个人中心操作 =====
  editProfile() {
    wx.navigateTo({ url: '/pages/profile/profile' });
  },

  manageFamily() {
    wx.navigateTo({ url: '/pages/profile/profile' });
  },

  manageDevices() {
    wx.showToast({ title: '设备管理开发中', icon: 'none' });
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
