const api = require('../../utils/api.js');

Page({
  data: {
    currentTab: 1,
    showInvitePopup: false,
    selectedRole: 'member',

    devices: [],
    userInfo: {
      nickname: '点击登录',
      id: '',
      avatar: '/images/DefaultAvatar.png',
      familyCount: 0,
      deviceCount: 0,
      familyName: '未加入家庭',
      memberCount: 0,
      members: []
    },

    menuList1: [
      { id: 1, icon: '🔋', name: '设备耗材', url: '/pages/consumables/consumables' },
      { id: 2, icon: '📱', name: '多端管理', url: '/pages/multiDevice/multiDevice' },
      { id: 3, icon: '📿', name: '设备管理', url: '/pages/deviceManage/deviceManage' },
      { id: 4, icon: '⚙️', name: '更多设置', url: '/pages/settings/settings' }
    ],

    menuList2: [
      { id: 5, icon: '🛍️', name: '在线商城', url: '/pages/joke/joke?type=star' },
      { id: 6, icon: '🐾', name: 'PetNode 服务', url: '/pages/joke/joke?type=star' },
      { id: 7, icon: '💬', name: '帮助与反馈', url: '/pages/joke/joke?type=star' }
    ],

    articles: [
      { id: 1, title: '了解您宠物的静息呼吸频率', desc: '静息呼吸频率是评估宠物心肺健康的重要黄金指标。', image: '/images/article_breathing.png' },
      { id: 2, title: '了解您宠物的睡眠质量', desc: '狗狗一天需要睡多久？教你如何通过睡姿和时长判断它的健康状况。', image: '/images/article_sleep.jpg' },
      { id: 3, title: '您知道宠物的房颤吗？', desc: '心房颤动不仅是人类的隐形杀手，同样也潜伏在许多高龄犬猫身边。', image: '/images/article_afib.jpg' },
      { id: 4, title: '了解您宠物的生命体征', desc: '体温、脉搏、呼吸：每一个养宠人都应该掌握的基础生命体征自测法。', image: '/images/article_vitals.jpg' }
    ],

    isDaytime: true
  },

  onLoad() {
    this.checkTime();
    this.fetchData();
  },

  onShow() {
    this.checkTime();
    const token = wx.getStorageSync('access_token');
    if (token) {
      this.fetchData();
    }
  },

  onPullDownRefresh() {
    this.fetchData().then(() => wx.stopPullDownRefresh());
  },

  async fetchData() {
    const token = wx.getStorageSync('access_token');
    if (!token) return;

    try {
      const [meData, familyData] = await Promise.all([
        api.get('/api/v1/me').catch(() => null),
        api.get('/api/v1/family/members').catch(() => null)
      ]);

      if (meData) this.buildUserInfo(meData);
      if (familyData) this.buildFamilyInfo(familyData);
    } catch (_) {
      // 静默处理，保留当前数据
    }
  },

  buildUserInfo(meData) {
    const pets = meData.pets || [];
    const devices = pets.map((p, i) => ({
      id: p.device_id,
      name: p.pet_name || p.device_id,
      status: '在线',
      avatar: p.avatar_url || '🐕'
    }));

    const avatar = meData.avatar_url || '/images/DefaultAvatar.png';
    const nickname = meData.nickname || 'PetNode 用户';
    const userId = meData.user_id || '';

    this.setData({
      devices,
      'userInfo.nickname': nickname,
      'userInfo.id': userId ? `ID: ${userId.substring(0, 8)}` : '',
      'userInfo.avatar': avatar,
      'userInfo.deviceCount': devices.length,
      user_id: userId,
    });
  },

  buildFamilyInfo(familyData) {
    const members = familyData.members || [];
    const memberAvatars = members.map(m => m.avatar_url || '/images/DefaultAvatar.png');

    this.setData({
      'userInfo.familyCount': 1,
      'userInfo.familyName': familyData.family_name || '我的小窝',
      'userInfo.memberCount': members.length,
      'userInfo.members': memberAvatars.length > 0 ? memberAvatars : ['/images/DefaultAvatar.png']
    });
  },

  checkTime() {
    const app = getApp();
    if (!app.globalData.autoTheme) {
      this.setData({ isDaytime: true });
      return;
    }
    const hour = new Date().getHours();
    const isDaytime = hour >= 6 && hour < 18;
    this.setData({ isDaytime });
  },

  /* ================= 2. 导航 & 滑动逻辑 ================= */

  onSwiperChange(e) {
    this.setData({ currentTab: e.detail.current });
  },

  switchTab(e) {
    const index = e.currentTarget.dataset.index;
    this.setData({ currentTab: index });
  },

  navToSubPage(e) {
    const url = e.currentTarget.dataset.url;
    if (url) {
      wx.navigateTo({ url });
    }
  },

  goToDetail(e) {
    const petId = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/petDetail/petDetail?id=${petId}` });
  },

  /* ================= 3. 扫码添加设备 ================= */

  scanDevice() {
    const that = this;
    wx.scanCode({
      success: async (res) => {
        console.log('[scan] 扫码结果:', res.result);
        // 支持格式：petnode:device:<device_id>  或纯 device_id
        let deviceId = res.result.trim();
        const m = deviceId.match(/petnode:device:([a-f0-9]+)/i);
        if (m) deviceId = m[1];

        if (!/^[a-f0-9]{8,}$/i.test(deviceId)) {
          wx.showModal({ title: '无效二维码', content: `无法识别设备：${res.result}`, showCancel: false });
          return;
        }

        // 弹窗让用户输入宠物名字
        wx.showModal({
          title: '发现新设备',
          content: `设备 ID：${deviceId}\n\n点击确定绑定，稍后可修改名称`,
          confirmText: '绑定',
          success: async (modalRes) => {
            if (!modalRes.confirm) return;
            try {
              await api.post('/api/v1/devices/bind', {
                device_id: deviceId,
                pet_name: '新狗狗'
              });
              wx.showToast({ title: '绑定成功', icon: 'success' });
              that.fetchData();
            } catch (err) {
              wx.showModal({
                title: '绑定失败',
                content: err.message || '该设备可能已被其他人绑定',
                showCancel: false
              });
            }
          }
        });
      },
      fail: (err) => {
        if (err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '扫码失败', icon: 'error' });
        }
      }
    });
  },

  /* ================= 4. 邀请家人弹窗逻辑 ================= */

  openInvitePopup() {
    this.setData({ showInvitePopup: true });
  },

  closeInvitePopup() {
    this.setData({ showInvitePopup: false });
  },

  selectRole(e) {
    this.setData({ selectedRole: e.currentTarget.dataset.role });
  },

  goToRemark() {
    this.closeInvitePopup();
    wx.navigateTo({ url: '/pages/inviteRemark/inviteRemark' });
  },

  goToLogin() {
    wx.navigateTo({ url: '/pages/login/login' });
  },

  handleLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (!res.confirm) return;
        wx.removeStorageSync('access_token');
        wx.removeStorageSync('user_id');
        getApp().globalData.token = null;
        this.setData({
          devices: [],
          user_id: '',
          'userInfo.nickname': '点击登录',
          'userInfo.id': '',
          'userInfo.avatar': '/images/DefaultAvatar.png',
          'userInfo.familyCount': 0,
          'userInfo.deviceCount': 0,
          'userInfo.familyName': '未加入家庭',
          'userInfo.memberCount': 0,
          'userInfo.members': []
        });
      }
    });
  }
})
