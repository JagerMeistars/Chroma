#ifndef CHROMA_EDITOR_GIZMO
#define CHROMA_EDITOR_GIZMO
// Axiom 6.1.2 uses vanilla shaders for its ALWAYS_PASS, depth-writing gizmos.
// Match its local meshes and uniform scale, never a screen/world-space region.
// ponytail: version-specific mesh signature; revise if Axiom changes its meshes.
bool chromaEditorGizmo(vec3 position, vec4 color, bool lines) {
    if (ProjMat[2][3] == 0.0) return false;
    vec3 scale = vec3(length(ModelViewMat[0].xyz), length(ModelViewMat[1].xyz), length(ModelViewMat[2].xyz));
    if (scale.x < 0.1 - 0.000001 ||
        any(greaterThan(abs(scale - vec3(scale.x)), vec3(max(0.000001, scale.x * 0.0001))))) return false;
    vec3 p = abs(position);
    bool grey = all(lessThan(abs(color.rgb - vec3(color.r)), vec3(0.000001)));
    if (!lines && color.a > 0.999999 && grey &&
        all(lessThan(abs(p - vec3(0.3)), vec3(0.000001)))) return true;
    if (color.a != 0.0 && abs(color.a - 128.0/255.0) > 0.000001 &&
        abs(color.a - 170.0/255.0) > 0.000001 && abs(color.a - 1.0) > 0.000001) return false;

    // Axis colours, including shaded arrows and highlighted/transparent handles.
    vec3 c = color.rgb;
    float lo = min(c.x, min(c.y, c.z)), hi = max(c.x, max(c.y, c.z));
    float mid = c.x + c.y + c.z - lo - hi;
    bool axisColor = hi > 0.0 && (mid < 0.000001 ||
        (abs(lo - mid) < 1.5 / 255.0 &&
         (abs(lo / hi - 0.6) < 0.015 || abs(lo / hi - 191.0/255.0) < 0.015 || abs(lo / hi - 128.0/255.0) < 0.015)));
    if (!axisColor && !grey) return false;
    float largest = max(p.x, max(p.y, p.z));
    float smallest = min(p.x, min(p.y, p.z));
    float middle = p.x + p.y + p.z - largest - smallest;
    float radius2 = dot(p, p);
    // Partially visible ring segments end inside a 64-segment chord.
    bool ring = radius2 >= 24.939 && radius2 <= 25.003;
    if (lines) {
        if (!((abs(hi - 191.0/255.0) < 0.000001 && abs(color.a - 170.0/255.0) < 0.000001) ||
              (abs(hi - 1.0) < 0.000001 && abs(color.a - 1.0) < 0.000001 && mid > 0.0))) return false;
        // Scale-drag endpoints move along the axis, including toward zero.
        bool axisEnd = middle < 0.00001;
        return axisColor && (ring || axisEnd);
    }
    bool cone = (abs(largest - 4.0) < 0.00001 && (middle < 0.00001 || abs(middle*middle + smallest*smallest - 0.071111111) < 0.00001))
             || (abs(largest - 4.8) < 0.00001 && middle < 0.00001);
    bool movePlane = smallest < 0.00001 &&
        (abs(middle - 1.65) < 0.00001 || abs(middle - 2.55) < 0.00001) &&
        (abs(largest - 1.65) < 0.00001 || abs(largest - 2.55) < 0.00001);
    bool scaleBox = abs(smallest - 0.3) < 0.00001 && abs(middle - 0.3) < 0.00001;
    // A rotation fan's transparent centre must agree with its perimeter depth.
    return (largest < 0.00001 && color.a == 0.0) ||
           (axisColor && (cone || movePlane || scaleBox || ring));
}
#endif
