# Draco for 3D Gaussian Splatting

This is a variant of [Google Draco Compression](https://google.github.io/draco/) to support [original 3D Gaussian splatting (3DGS)](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/) content.

Draco is an open-source library for compressing and decompressing 3D geometric meshes and point clouds. It is intended to improve the storage and transmission of 3D graphics.

However, this project is only focused on encode and decode 3DGS, so compressing 3D meshes or 3D point cloud is not supported.

## Build (C++ execution)

### Build (Ubuntu and MACOS)
```bash
mkdir build_dir && cd build_dir
cmake ../
make
```

## Build (Javascript WebAssembly) (Test in MACOS)
```bash
mkdir build_dir && cd build_dir
export EMSCRIPTEN=/path_to_emsdk/upstream/emscripten
# for example: export EMSCRIPTEN=/Users/syjintw/Desktop/MMSys25_RU/emsdk/upstream/emscripten
cmake ../ -DCMAKE_TOOLCHAIN_FILE=/path_to_emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake -DDRACO_WASM=ON
# for example: cmake ../ -DCMAKE_TOOLCHAIN_FILE=/Users/syjintw/Desktop/MMSys25_RU/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake -DDRACO_WASM=ON
make
java -jar ../additional/closure-compiler-v20210302.jar --compilation_level SIMPLE --js draco_decoder.js --js_output_file draco_wasm_wrapper.js
```

## Usage
**[!] You should change the 3DGS data to ASCII format before you encode.**

## Change binary format to ASCII format
```bash
python ./mytool/3DGS_pcd_to_draco_pcd.py -i ./myData/ficus.ply -o ./myData/ficus_3dgs.ply
```

## Encode (C++ execution)
### Simple
```bash
./build_dir/draco_encoder -point_cloud \
-i ./myData/ficus_3dgs.ply \
-o ./myData/ficus_3dgs_compressed.drc
```

### More complex setup
```bash
./build_dir/draco_encoder -point_cloud \
-i ./myData/ficus_3dgs.ply \
-o ./myData/ficus_3dgs_compressed.drc \
-qp 16 \
-qfd 16 -qfr1 16 -qfr2 16 -qfr3 16 \
-qo 16 \
-qs 16 -qr 16 \
-cl 10
```

## Decode (C++ execution)
```bash
./build_dir/draco_decoder \
-i ./myData/ficus_3dgs_compress.drc \
-o ./myData/ficus_3dgs_distorted.ply
```

## Decode (Javascript)

Check the html file (`/draco_adjusted/javascript/time_draco_decode.html`)
There are some important path need to change, and you can search them using `//! [YC]` as the searching keyword. Good Luck!!

Open the web server using the following command in the root folder
```
python -m http.server
```


# For Experiment
## Encode (Using my_encode.py and json file)
```bash
python my_encoder.py -jp ../myJson/template_sh0.json
```

## Decode (Using my_decode.py and json file)
```bash
python my_decoder.py -jp ../myJson/template.json
```

## Configuration json file
Based on the template json file at `myJson/template.json`


## Contributing

Pull requests are welcome. For major changes, please open an issue first
to discuss what you would like to change.

Please make sure to update tests as appropriate.

<!-- ## License

[MIT](https://choosealicense.com/licenses/mit/) -->
