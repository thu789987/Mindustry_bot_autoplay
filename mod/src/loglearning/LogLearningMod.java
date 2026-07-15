package loglearning;

import arc.Events;
import arc.files.Fi;
import arc.util.Log;
import arc.util.serialization.Jval;
import mindustry.game.EventType.BlockBuildEndEvent;
import mindustry.game.EventType.BuildRotateEvent;
import mindustry.game.EventType.ConfigEvent;
import mindustry.game.EventType.PlayEvent;
import mindustry.game.EventType.ResetEvent;
import mindustry.gen.Building;
import mindustry.mod.Mod;
import mindustry.type.Item;
import mindustry.type.Liquid;
import mindustry.world.Tile;

import java.io.IOException;
import java.io.Writer;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

import static mindustry.Vars.dataDirectory;
import static mindustry.Vars.player;
import static mindustry.Vars.world;

/**
 * Ghi log hanh dong xay dung (place/remove/configure/rotate) cua nguoi choi
 * ra file JSONL, dung dinh dang "actions" ma bot/log_learning.py (phia
 * Python, xem repo mindustry-factory-ai) da ho tro tu truoc:
 *
 *   {"op": "place", "building": "conveyor", "x": 10, "y": 5, "rotation": 0}
 *   {"op": "remove", "x": 10, "y": 5}
 *   {"op": "configure", "x": 10, "y": 5, "value": "coal"}
 *   {"op": "rotate", "x": 10, "y": 5, "rotation": 2}
 *
 * Bat dung 3 su kien that cua Mindustry (xem reference/EventType.java trong
 * repo Python -- da doi chieu tung field truoc khi viet file nay):
 *   - BlockBuildEndEvent(tile, unit, team, breaking, config) -- place/remove
 *   - ConfigEvent(tile: Building, player, value)              -- configure
 *   - BuildRotateEvent(build, unit, previous)                  -- rotate
 *
 * Moi phien choi (PlayEvent) tao 1 thu muc rieng trong
 * <data>/log-learning/<timestamp>/ gom:
 *   - initial_state.json  : dung dinh dang bot/state.py ky vong (ore_tiles,
 *     liquid_tiles, buildings da co san khi bat dau phien)
 *   - actions.jsonl        : moi dong 1 hanh dong, theo dung thu tu xay ra
 *
 * Dung tiep bang cach goi (Python):
 *   from bot.log_learning import extract_feedback_from_log
 *   extract_feedback_from_log(initial_state, log_actions, scorer)
 * (doc initial_state.json + parse tung dong actions.jsonl thanh list dict).
 *
 * GIOI HAN (ghi ro, khong giau -- xem mod/README.md muc "Gioi han"):
 *   - Chi ghi hanh dong cua TEAM cua player cuc bo (khong phan biet unit nao
 *     trong team thuc hien -- drone tu xay theo blueprint cua player van
 *     tinh la "y dinh cua player").
 *   - ConfigEvent.value chi anh xa dung sang schema Python cho Item/Liquid/
 *     boolean/so (vd: sorter loc item). Cac kieu config khac (Point2 cho
 *     bridge/mass-driver link, mang Point2[]...) ghi tam thanh chuoi
 *     String.valueOf(...) de khong mat du lieu, nhung bot/log_learning.py
 *     hien khong doc duoc field nay cho cac loai building do.
 *   - Chi hoat dong dung khi mod nay chay o phia MO PHONG THE GIOI THAT (map
 *     don, hoac may dang la host cua server) -- neu vao server cua nguoi
 *     khac ma ho khong cai mod nay, cac su kien tren khong duoc phat sinh o
 *     may minh.
 *   - initial_state.json chi ghi type/x/y/rotation cho building co san luc
 *     bat dau phien -- khong suy luan lai ore_target cua drill co san tu
 *     truoc (drill dat MOI trong luc choi thi CO duoc suy ra qua ConfigEvent
 *     neu game phat sinh, nhung Drill that khong configurable ore -- game tu
 *     chon ore chiem da so trong footprint, nen field ore_target cho drill
 *     co san se la null; khong anh huong toi simulator vi bot/state.py coi
 *     day la optional).
 */
public class LogLearningMod extends Mod{
    private static final DateTimeFormatter STAMP_FORMAT = DateTimeFormatter.ofPattern("yyyy-MM-dd_HH-mm-ss");

    private Writer actionsWriter;

    public LogLearningMod(){
        Log.info("[log-learning] mod da nap");

        Events.on(PlayEvent.class, e -> startSession());
        Events.on(ResetEvent.class, e -> closeSession());

        Events.on(BlockBuildEndEvent.class, e -> {
            if(e.breaking){
                writeAction(Jval.newObject()
                    .put("op", "remove")
                    .put("x", (int)e.tile.x)
                    .put("y", (int)e.tile.y));
                return;
            }

            Building building = e.tile.build;
            if(building == null || building.block == null) return;
            if(building.team != player.team) return;

            writeAction(Jval.newObject()
                .put("op", "place")
                .put("building", building.block.name)
                .put("x", building.tileX())
                .put("y", building.tileY())
                .put("rotation", building.rotation));
        });

        Events.on(ConfigEvent.class, e -> {
            if(e.tile == null || e.tile.block == null) return;
            if(e.tile.team != player.team) return;

            writeAction(Jval.newObject()
                .put("op", "configure")
                .put("x", e.tile.tileX())
                .put("y", e.tile.tileY())
                .put("value", configValueToJval(e.value)));
        });

        Events.on(BuildRotateEvent.class, e -> {
            if(e.build == null) return;
            if(e.build.team != player.team) return;

            writeAction(Jval.newObject()
                .put("op", "rotate")
                .put("x", e.build.tileX())
                .put("y", e.build.tileY())
                .put("rotation", e.build.rotation));
        });
    }

    /** ConfigEvent.value co the la nhieu kieu (xem EventType.java that: Object
     * value) -- chi Item/Liquid/boolean/so anh xa dung sang schema Python
     * hien tai; con lai ghi tam thanh string, xem GIOI HAN o dau file. */
    private Jval configValueToJval(Object value){
        if(value == null) return Jval.NULL;
        if(value instanceof Item item) return Jval.valueOf(item.name);
        if(value instanceof Liquid liquid) return Jval.valueOf(liquid.name);
        if(value instanceof Boolean bool) return Jval.valueOf((boolean)bool);
        if(value instanceof Integer i) return Jval.valueOf((int)i);
        if(value instanceof Float f) return Jval.valueOf((float)f);
        return Jval.valueOf(String.valueOf(value));
    }

    private void startSession(){
        closeSession();

        String stamp = STAMP_FORMAT.format(LocalDateTime.now());
        Fi sessionDir = dataDirectory.child("log-learning").child(stamp);
        sessionDir.mkdirs();

        dumpInitialState(sessionDir.child("initial_state.json"));

        try{
            actionsWriter = sessionDir.child("actions.jsonl").writer(false, "UTF-8");
        }catch(Exception ex){
            Log.err("[log-learning] khong mo duoc actions.jsonl", ex);
            actionsWriter = null;
            return;
        }

        Log.info("[log-learning] bat dau phien log tai @", sessionDir.absolutePath());
    }

    private void closeSession(){
        if(actionsWriter == null) return;
        try{
            actionsWriter.close();
        }catch(IOException ex){
            Log.err("[log-learning] loi khi dong actions.jsonl", ex);
        }
        actionsWriter = null;
    }

    /** Ghi 1 dong JSON + newline, flush ngay (hanh dong xay dung la theo nhip
     * nguoi choi, khong phai moi tick, nen flush lien tuc khong anh huong
     * hieu nang dang ke, doi lai khong mat du lieu neu game crash). */
    private void writeAction(Jval record){
        if(actionsWriter == null) return;
        try{
            actionsWriter.write(record.toString(Jval.Jformat.plain));
            actionsWriter.write("\n");
            actionsWriter.flush();
        }catch(IOException ex){
            Log.err("[log-learning] loi khi ghi actions.jsonl", ex);
        }
    }

    /** Dump trang thai ban dau (ore_tiles/liquid_tiles/buildings da co san)
     * dung dinh dang bot/state.py ky vong -- xem docstring bot/state.py
     * trong repo Python de doi chieu. */
    private void dumpInitialState(Fi outFile){
        Jval oreTiles = Jval.newArray();
        Jval liquidTiles = Jval.newArray();
        Jval buildings = Jval.newArray();

        int width = world.width();
        int height = world.height();

        for(int x = 0; x < width; x++){
            for(int y = 0; y < height; y++){
                Tile tile = world.tile(x, y);
                if(tile == null) continue;

                if(tile.overlay() != null && tile.overlay().itemDrop != null){
                    oreTiles.add(Jval.newObject()
                        .put("x", x)
                        .put("y", y)
                        .put("ore", tile.overlay().itemDrop.name));
                }

                if(tile.floor() != null && tile.floor().liquidDrop != null){
                    liquidTiles.add(Jval.newObject()
                        .put("x", x)
                        .put("y", y)
                        .put("liquid", tile.floor().liquidDrop.name));
                }

                Building build = tile.build;
                if(build != null && build.tile == tile && build.block != null && build.team == player.team){
                    buildings.add(Jval.newObject()
                        .put("type", build.block.name)
                        .put("x", build.tileX())
                        .put("y", build.tileY())
                        .put("rotation", build.rotation));
                }
            }
        }

        Jval root = Jval.newObject()
            .put("width", width)
            .put("height", height)
            .put("ore_tiles", oreTiles)
            .put("liquid_tiles", liquidTiles)
            .put("buildings", buildings);

        try{
            outFile.writeString(root.toString(Jval.Jformat.plain), false, "UTF-8");
        }catch(Exception ex){
            Log.err("[log-learning] khong ghi duoc initial_state.json", ex);
        }
    }
}
