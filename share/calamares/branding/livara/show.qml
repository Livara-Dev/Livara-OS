import QtQuick 2.12
Rectangle {
    color: "#050408"
    Column {
        anchors.centerIn: parent
        spacing: 28
        Image { source: "logo.png"; width: 160; height: 160; anchors.horizontalCenter: parent.horizontalCenter; fillMode: Image.PreserveAspectFit }
        Text { text: "A space that feels like you."; color: "#e9d9ff"; font.pixelSize: 28; anchors.horizontalCenter: parent.horizontalCenter }
        Text { text: "Livara OS · Your desktop, your possibilities"; color: "#b5a2cc"; font.pixelSize: 16; anchors.horizontalCenter: parent.horizontalCenter }
    }
}
