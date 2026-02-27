find_package(pybind11 REQUIRED)

pybind11_add_module(_dracogs dracogs_bindings.cc)

target_include_directories(_dracogs PRIVATE
  "${draco_root}/src"
  "${draco_build}")

target_link_libraries(_dracogs PRIVATE draco_static)

# Ensure we pull in all object library objects that draco_static was built from
foreach(objlib ${draco_object_library_deps})
  target_sources(_dracogs PRIVATE $<TARGET_OBJECTS:${objlib}>)
endforeach()
