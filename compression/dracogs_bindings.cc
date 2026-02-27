#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <memory>
#include <stdexcept>
#include <string>

#include "draco/attributes/geometry_attribute.h"
#include "draco/attributes/point_attribute.h"
#include "draco/compression/decode.h"
#include "draco/compression/encode.h"
#include "draco/compression/expert_encode.h"
#include "draco/core/encoder_buffer.h"
#include "draco/core/decoder_buffer.h"
#include "draco/point_cloud/point_cloud.h"

namespace py = pybind11;

using FloatArray = py::array_t<float, py::array::c_style | py::array::forcecast>;

namespace {

int add_attribute_from_numpy(draco::PointCloud &pc,
                             draco::GeometryAttribute::Type type,
                             const FloatArray &arr) {
  auto buf = arr.unchecked<2>();
  const int64_t num_points = buf.shape(0);
  const int num_components = static_cast<int>(buf.shape(1));

  draco::GeometryAttribute ga;
  ga.Init(type, nullptr, num_components, draco::DT_FLOAT32, false,
          sizeof(float) * num_components, 0);
  const int att_id = pc.AddAttribute(ga, true, num_points);

  auto *att = pc.attribute(att_id);
  for (int64_t i = 0; i < num_points; ++i) {
    att->SetAttributeValue(draco::AttributeValueIndex(static_cast<uint32_t>(i)),
                           buf.data(i, 0));
  }
  return att_id;
}

FloatArray extract_attribute(const draco::PointCloud &pc,
                             draco::GeometryAttribute::Type type) {
  const int att_id = pc.GetNamedAttributeId(type);
  if (att_id < 0) {
    return FloatArray();  // empty array signals "not present"
  }
  const auto *att = pc.attribute(att_id);
  const int64_t num_points = pc.num_points();
  const int num_components = att->num_components();

  FloatArray result({num_points, static_cast<int64_t>(num_components)});
  auto out = result.mutable_unchecked<2>();
  for (int64_t i = 0; i < num_points; ++i) {
    att->GetMappedValue(draco::PointIndex(static_cast<uint32_t>(i)),
                        out.mutable_data(i, 0));
  }
  return result;
}

}  // namespace


static py::bytes encode(
    const FloatArray &positions,
    const FloatArray &f_dc,
    const FloatArray &f_rest_1,
    const FloatArray &f_rest_2,
    const FloatArray &f_rest_3,
    const FloatArray &opacity,
    const FloatArray &scale,
    const FloatArray &rotation,
    int qp, int qfd, int qfr1, int qfr2, int qfr3,
    int qo, int qs, int qr, int cl) {

  const int64_t num_points = positions.shape(0);
  if (num_points == 0) {
    throw std::runtime_error("positions array is empty");
  }

  draco::PointCloud pc;
  pc.set_num_points(static_cast<uint32_t>(num_points));

  add_attribute_from_numpy(pc, draco::GeometryAttribute::POSITION, positions);
  add_attribute_from_numpy(pc, draco::GeometryAttribute::F_DC, f_dc);

  bool has_fr1 = (f_rest_1.size() > 0 && qfr1 >= 0);
  bool has_fr2 = (f_rest_2.size() > 0 && qfr2 >= 0);
  bool has_fr3 = (f_rest_3.size() > 0 && qfr3 >= 0);

  if (has_fr1) add_attribute_from_numpy(pc, draco::GeometryAttribute::F_REST_1, f_rest_1);
  if (has_fr2) add_attribute_from_numpy(pc, draco::GeometryAttribute::F_REST_2, f_rest_2);
  if (has_fr3) add_attribute_from_numpy(pc, draco::GeometryAttribute::F_REST_3, f_rest_3);

  add_attribute_from_numpy(pc, draco::GeometryAttribute::OPACITY, opacity);
  add_attribute_from_numpy(pc, draco::GeometryAttribute::SCALE, scale);
  add_attribute_from_numpy(pc, draco::GeometryAttribute::ROT, rotation);

  draco::Encoder encoder;
  const int speed = 10 - cl;
  encoder.SetSpeedOptions(speed, speed);

  if (qp > 0)   encoder.SetAttributeQuantization(draco::GeometryAttribute::POSITION, qp);
  if (qfd > 0)  encoder.SetAttributeQuantization(draco::GeometryAttribute::F_DC, qfd);
  if (qfr1 > 0) encoder.SetAttributeQuantization(draco::GeometryAttribute::F_REST_1, qfr1);
  if (qfr2 > 0) encoder.SetAttributeQuantization(draco::GeometryAttribute::F_REST_2, qfr2);
  if (qfr3 > 0) encoder.SetAttributeQuantization(draco::GeometryAttribute::F_REST_3, qfr3);
  if (qo > 0)   encoder.SetAttributeQuantization(draco::GeometryAttribute::OPACITY, qo);
  if (qs > 0)   encoder.SetAttributeQuantization(draco::GeometryAttribute::SCALE, qs);
  if (qr > 0)   encoder.SetAttributeQuantization(draco::GeometryAttribute::ROT, qr);

  std::unique_ptr<draco::ExpertEncoder> expert_encoder(
      new draco::ExpertEncoder(pc));
  expert_encoder->Reset(encoder.CreateExpertEncoderOptions(pc));

  draco::EncoderBuffer buffer;
  const draco::Status status = expert_encoder->EncodeToBuffer(&buffer);
  if (!status.ok()) {
    throw std::runtime_error(std::string("Draco encode failed: ") +
                             status.error_msg());
  }

  return py::bytes(buffer.data(), buffer.size());
}


static py::dict decode(const py::bytes &data) {
  const std::string raw = data;  // zero-copy view from pybind11
  draco::DecoderBuffer buffer;
  buffer.Init(raw.data(), raw.size());

  auto type_statusor = draco::Decoder::GetEncodedGeometryType(&buffer);
  if (!type_statusor.ok()) {
    throw std::runtime_error("Failed to determine geometry type");
  }
  if (type_statusor.value() != draco::POINT_CLOUD) {
    throw std::runtime_error("Expected point cloud geometry type");
  }

  draco::Decoder decoder;
  auto statusor = decoder.DecodePointCloudFromBuffer(&buffer);
  if (!statusor.ok()) {
    throw std::runtime_error(std::string("Draco decode failed: ") +
                             statusor.status().error_msg());
  }
  std::unique_ptr<draco::PointCloud> pc = std::move(statusor).value();

  py::dict result;
  result["num_points"] = static_cast<int64_t>(pc->num_points());

  auto try_extract = [&](const char *name, draco::GeometryAttribute::Type type) {
    FloatArray arr = extract_attribute(*pc, type);
    if (arr.size() > 0) {
      result[name] = arr;
    }
  };

  try_extract("positions", draco::GeometryAttribute::POSITION);
  try_extract("f_dc",      draco::GeometryAttribute::F_DC);
  try_extract("f_rest_1",  draco::GeometryAttribute::F_REST_1);
  try_extract("f_rest_2",  draco::GeometryAttribute::F_REST_2);
  try_extract("f_rest_3",  draco::GeometryAttribute::F_REST_3);
  try_extract("opacity",   draco::GeometryAttribute::OPACITY);
  try_extract("scale",     draco::GeometryAttribute::SCALE);
  try_extract("rotation",  draco::GeometryAttribute::ROT);

  return result;
}


PYBIND11_MODULE(_dracogs, m) {
  m.doc() = "DracoGS: In-memory 3D Gaussian Splat compression via modified Draco";

  m.def("encode", &encode,
        py::arg("positions"),
        py::arg("f_dc"),
        py::arg("f_rest_1"),
        py::arg("f_rest_2"),
        py::arg("f_rest_3"),
        py::arg("opacity"),
        py::arg("scale"),
        py::arg("rotation"),
        py::arg("qp")   = 16,
        py::arg("qfd")  = 16,
        py::arg("qfr1") = 16,
        py::arg("qfr2") = 16,
        py::arg("qfr3") = 16,
        py::arg("qo")   = 16,
        py::arg("qs")   = 16,
        py::arg("qr")   = 16,
        py::arg("cl")   = 7,
        R"doc(
Encode 3D Gaussian Splat attributes into a Draco compressed bitstream.

Parameters
----------
positions : np.ndarray[float32], shape (N, 3)
f_dc : np.ndarray[float32], shape (N, 3)
f_rest_1 : np.ndarray[float32], shape (N, 9) or empty
f_rest_2 : np.ndarray[float32], shape (N, 15) or empty
f_rest_3 : np.ndarray[float32], shape (N, 21) or empty
opacity : np.ndarray[float32], shape (N, 1)
scale : np.ndarray[float32], shape (N, 3)
rotation : np.ndarray[float32], shape (N, 4)
qp, qfd, qfr1, qfr2, qfr3, qo, qs, qr : int
    Quantization bits (0=lossless, 1-30 bits). Negative drops the attribute.
cl : int
    Compression level 0-10 (higher = slower but smaller).

Returns
-------
bytes
    Compressed Draco bitstream.
)doc");

  m.def("decode", &decode,
        py::arg("data"),
        R"doc(
Decode a Draco compressed bitstream back into 3D Gaussian Splat attributes.

Parameters
----------
data : bytes
    Compressed Draco bitstream (as returned by encode()).

Returns
-------
dict
    Keys: "num_points", "positions", "f_dc", "f_rest_1" (if present),
    "f_rest_2" (if present), "f_rest_3" (if present), "opacity",
    "scale", "rotation". Values are np.ndarray[float32].
)doc");
}
