# 照片时序档案

一个适合云服务器部署的极简照片展示网站，支持上传照片，并按拍摄时间生成时间线。

默认情况下，所有访客都只能查看时间线。只有配置了 GitHub 账号验证或管理员密码并登录后，才可以上传照片。
管理员登录后也可以删除照片。
上传时会自动读取照片 EXIF 中的拍摄时间；如果没有 EXIF，就按上传时间归档。页面展示的是缩略图，点击后会打开原图。
管理员还可以修改照片标题、原文件名、拍摄时间、上传时间、相机型号、镜头型号、35mm 等效焦距、光圈、快门速度、ISO 和备注。

## 特性

- 支持多张照片上传
- 按时间线展示照片
- 轻量本地存储，照片保存在 `uploads/`，元数据保存在 `data/photos.json`
- 中文字体使用 `/root/resource/font/NOTOSERIFSC-VF.TTF`
- 英文字体使用 `/root/resource/font/SigmaFont.TTF`
- 轻量大图预览弹层

## 启动

推荐直接使用 conda 环境：

```bash
cd /root/app/photo_timeline_site
/root/miniconda3/bin/conda env create -f environment.yml
source /root/miniconda3/etc/profile.d/conda.sh
conda activate photo-timeline
python app.py
```

如果你已经有 `photo-timeline` 环境，只需要更新依赖：

```bash
cd /root/app/photo_timeline_site
/root/miniconda3/bin/conda install -n photo-timeline pillow -y
```

如果你的 shell 里还没有 conda 命令，先执行：

```bash
source /root/miniconda3/etc/profile.d/conda.sh
```

默认监听 `0.0.0.0:8000`。

## 生产部署

```bash
cd /root/app/photo_timeline_site
gunicorn -w 2 -b 0.0.0.0:8000 app:app
```

如果想完全避免激活环境，可以直接用：

```bash
/root/miniconda3/bin/conda run -n photo-timeline gunicorn -w 2 -b 0.0.0.0:8000 app:app
```

如果字体文件位置不同，可以设置：

```bash
export PHOTO_FONT_DIR=/root/resource/font
```

如果要启用管理员上传，请额外设置：

```bash
export ADMIN_PASSWORD=your-strong-password
export SECRET_KEY=your-session-secret
```

如果你想改成 GitHub 账号验证，建议在 GitHub 创建 OAuth App，并设置回调地址为：

```bash
https://your-domain.example/admin/github/callback
```

然后配置这些环境变量：

```bash
export GITHUB_CLIENT_ID=your-github-oauth-client-id
export GITHUB_CLIENT_SECRET=your-github-oauth-client-secret
export GITHUB_ALLOWED_USERS=your-github-username
```

如果你部署在反向代理后面，或者想手动固定回调地址，也可以额外设置：

```bash
export GITHUB_CALLBACK_URL=https://your-domain.example/admin/github/callback
```

管理员登录入口是 `/admin/login`，如果 GitHub 验证已配置，首页管理员按钮会直接跳转到 GitHub 登录；登录后首页右侧才会显示上传表单。
管理员可在每张照片右侧点击“修改信息”来修正标题、拍摄时间和说明。

## 存储说明

- 上传图片：`uploads/`
- 缩略图：`thumbnails/`
- 照片元数据：`data/photos.json`

## 依赖文件

- `environment.yml`：conda 环境定义
- `requirements.txt`：Python 依赖清单，方便迁移到其他安装方式
