form.addEventListener('submit', async (e) => {
  e.preventDefault()
  const ten = document.getElementById('ten').value.trim()
  const mo_ta = document.getElementById('mo_ta').value.trim()
  const gia = parseInt(document.getElementById('gia').value, 10) || 0
  const danh_muc_id = document.getElementById('danh_muc_id').value
  const fileInput = document.getElementById('hinh_anh')

  if (!ten || !danh_muc_id) {
    alert('Vui lòng nhập đủ thông tin')
    return
  }

  const formData = new FormData()
  formData.append('ten_san_pham', ten)
  formData.append('mo_ta', mo_ta)
  formData.append('gia', gia)
  formData.append('danh_muc_id', danh_muc_id)
  if (fileInput.files.length > 0) {
    formData.append('hinh_anh', fileInput.files[0])
  }

  const res = await fetch("{% url 'shop:api_products_create' %}", {
    method: 'POST',
    headers: { 'X-CSRFToken': CSRF }, // KHÔNG set Content-Type
    body: formData
  })

  if (res.ok) {
    window.location = "{% url 'shop:admin_products' %}"
  } else {
    const err = await res.json().catch(() => ({}))
    alert(err.error || 'Tạo sản phẩm thất bại')
  }
})
