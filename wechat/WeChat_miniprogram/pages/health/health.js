const API = require('../../utils/api.js');

Page({
  data: {
    pets: [],
    loading: false
  },

  onShow() {
    this.loadPetsWithHealth();
  },

  async loadPetsWithHealth() {
    if (this.data.loading) return;
    this.setData({ loading: true });
    try {
      const res = await API.fetchPets();
      const pets = res.pets || [];

      // 并发拉取每只宠物的概览数据
      const enriched = await Promise.all(
        pets.map(async (pet) => {
          try {
            const summary = await API.fetchPetSummary(pet.pet_id);
            return { ...pet, summary };
          } catch (err) {
            return { ...pet, summary: null };
          }
        })
      );

      this.setData({ pets: enriched });
    } catch (err) {
      console.error('加载健康数据失败:', err);
    } finally {
      this.setData({ loading: false });
    }
  },

  goToDetail(e) {
    const petId = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/petDetail/petDetail?id=${petId}` });
  }
});
